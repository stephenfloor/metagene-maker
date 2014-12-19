# binning_functions.py
# 8/29/14
# helper functions to make bins for each region

import os, glob, csv, re, collections, math, multiprocessing, sys, time
from datetime import datetime

# gets the average score within this bin
def getAverageScore(readList, currStart, currEnd, binNum, rn):
	totalLength = currEnd - currStart + 1
	totalScore = 0
	readNumber = rn 			# which read to start at

	while True:
		read = readList[readNumber]
		readStart, readEnd, score = read[0], read[1], read[2]
		#print 'read', readStart, readEnd, score

		if readEnd < currStart:
			readNumber += 1 	# never read that read again
			continue 			# moves on to next read
		if currEnd < readStart: 
			#print 'totalScore', totalScore
			break 				# end of gene < start of read. No coverage, so score is 0

		if currStart < readStart: currStart = readStart # ignore zeros that are in the read region
		if readEnd >= currEnd: 	# end of gene is within the read
			totalScore += score * (currEnd - currStart + 1)
			#print 'totalScore', totalScore, currEnd - currStart + 1
			break				# don't advance read number because the read extends past end of gene
		else: # end of gene is past the read
			totalScore += score * (readEnd - currStart + 1)
			#print 'totalScore', totalScore, readEnd - currStart + 1
			readNumber += 1 	# advance read number because this read won't be needed anymore

		currStart = readEnd + 1

	return float(totalScore)/totalLength, readNumber

# gets the array of bins for each gene
def getBins(chrom, start, end, numBins, rn, reads, binLength):

	currStart = start
	binNum = start/binLength    

	# better way to find the initial readnumber; saves a few seconds
	readNumber = 0 #index of read, updated each time
	readList = reads[chrom][binNum]
	left = 0
	right = len(readList) - 1	
	curr = 0
	while True:
		curr = (left + right)/2
		#print curr, currStart, readList[curr]
		#time.sleep(0.3)
		if curr == left or curr == right: break
		if currStart < readList[curr][0]: right = curr
		else: left = curr					
	
	# walking through each bin for the region
	# tstart = datetime.now()
	# for i in range(100):
	scores = []
	readNumber = curr-1		
	spacingPerBin = int(math.ceil((end - start)/float(numBins)))

	while currStart < end:
		currEnd = currStart + spacingPerBin - 1 # end of my window
		if currEnd > end: currEnd = end # last bin can't go past TES
		
		# xstart = datetime.now()
		# for i in range(100):
		score, readNumber = getAverageScore(readList, currStart, currEnd, binNum, readNumber) #updates read number also
		# xend = datetime.now()
		# delta = xend - xstart
		# print delta.total_seconds()
		
		#print readNumber, currStart, currEnd, readList[readNumber]
		#time.sleep(0.3)
		scores.append(score)
		currStart = currEnd + 1 # new start of my window
	# tend = datetime.now()
	# delta = tend - tstart
	# print delta.total_seconds()

	return scores

# for each chromosome, get bins corresponding to each region in the chromosome
def regionWorker(binFolder, regionType, chrom, chrToRegion, startCol, endCol, stranded, folderStrand, strandCol, limitSize, numBins, extendRegion, reads, binLength):
	ofile = open(binFolder + "/" + regionType + "/" + chrom + ".txt", 'w')
	writer = csv.writer(ofile, 'textdialect')

	for region in chrToRegion[chrom]:
		start = int(region[startCol])
		end = int(region[endCol])
		
		#print "SNF: regionworker start %d end %d limitSize %r region %s" % (start, end, limitSize, region)

		# binning doesn't really make sense here so just ignore
		if limitSize:
			if end - start < 200 or end - start > 200000: continue 

		# extending to 1x upstream and downstream
		if extendRegion:
			length = end - start
			start = start - length
			end = end + length
			region[startCol] = start
			region[endCol] = end
			
		# only taking the regions that match the strand of bedgraph, 
		# if bedgraph and region file are both stranded
		strand = region[strandCol]
		#if folderStrand != '0' and stranded and strand != folderStrand: continue 

		# getting bins and reading from end to start if region is antisense
		regionBins = getBins(chrom, start, end, numBins, 0, reads, binLength)
		if stranded and strand == '-': regionBins = regionBins[::-1] 

		outputRow = region
		outputRow.append(sum(regionBins)) 
		outputRow.extend(regionBins)
		writer.writerow(outputRow)

	ofile.close()
	
def regionProcess(binFolder, regionType, chrToRegion, chroms, startCol, endCol, stranded, folderStrand, strandCol, limitSize, numBins, extendRegion, reads, binLength):
	print "Working on " + regionType
	procs = []
	for chrom in chroms:
		if chrom not in reads: continue
		p = multiprocessing.Process(target=regionWorker, args=(binFolder, regionType, chrom, chrToRegion, startCol, endCol, stranded, folderStrand, strandCol, limitSize, numBins, extendRegion, reads, binLength))
		procs.append(p)
		p.start()
	for p in procs:
		p.join()	# wait till all are done before moving on
		











		
# Loading reads for each bedgraph, for each chromosome
def getReads(readQueue, chrom, graph, binLength):
	ifile = open(graph, 'r')
	reader = csv.reader(ifile, 'textdialect')
	readsForChrom = {}

	for row in reader:
		start = int(row[1])
		end = int(row[2])
		score = float(row[3])

		# which bins does each interval go into?
		binNum = start/binLength
		bin1 = binNum
		bin2 = bin1 - 1
		
		# result: bins are overlapping
		if bin1 not in readsForChrom.keys(): readsForChrom[bin1] = []
		readsForChrom[bin1].append([start, end, score])
		if bin2 not in readsForChrom.keys(): readsForChrom[bin2] = []
		readsForChrom[bin2].append([start, end, score])

	ifile.close()
	readQueue.put((chrom, readsForChrom))
	print chrom, 'done'

def readBedGraph(ifolder, chroms, binLength):
	manager = multiprocessing.Manager()
	readQueue = manager.Queue()

	# get all chromosomes in a queue
	procs = []
	for chrom in chroms:
		if not glob.glob(ifolder + chrom + '.bedGraph'): continue
		print chrom, ifolder + chrom + '.bedGraph'
		p = multiprocessing.Process(target=getReads, args=(readQueue, chrom, ifolder + chrom + '.bedGraph', binLength))
		p.start()
		procs.append(p)
	for proc in procs: proc.join()

	# make a large dictionary
	reads = {}
	if readQueue.qsize() == 0: return reads # no chromosomes
	print "Making dictionary"
	while not readQueue.empty():
		readTuple = readQueue.get()
		reads[readTuple[0]] = readTuple[1]
	return reads
