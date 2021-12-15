#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import dbm
import json
import socket
import shutil

def doFileSystemBackup(config, dumpFileName):
  dumpFilePath = str.join("/", [ config['BackupDir'], dumpFileName ])
  dumpFileDict = analyzeDumpFileName(dumpFileName)
  dumpFileLevel = dumpFileDict['dumpLevel']
  dumpFileSystem = "/" + str.join("/", [ dumpFileDict['backupFilesystem'] ] )
  sudoExecutable = shutil.which("sudo")
  if sudoExecutable is None:
    print("ERROR: Can not find sudo executable, quitting!")
    sys.exit(1)
  xfsdumpExecutable = shutil.which("xfsdump")
  if xfsdumpExecutable is None:
    print("ERROR: Can not find xfsdump executable, quitting!")
    sys.exit(1)
  xfsdumpCommand = [ sudoExecutable, xfsdumpExecutable, "-F", "-f", dumpFilePath, "-l", str(dumpFileLevel), dumpFileSystem ]
  print("Will execute following command:")
  print(xfsdumpCommand)
  with subprocess.Popen(xfsdumpCommand, stdout=subprocess.PIPE, universal_newlines=True) as xfsdumpProcess:
    print(xfsdumpProcess.stdout.read())

def analyzeDumpDir(backupDir):
  dumpedFilesList = []
  for backupDirInstance in os.scandir(backupDir):
    if backupDirInstance.is_file():
      if backupDirInstance.name.rpartition(".")[2] == "xfsdump":
        foundDumpFileInstance_dict = analyzeDumpFileName(backupDirInstance.name)
        foundDumpFileInstance_dict["mtime"] = backupDirInstance.stat().st_mtime
        foundDumpFileInstance_dict["path"] = backupDirInstance.path
        dumpedFilesList.append(foundDumpFileInstance_dict)
  return dumpedFilesList

def convertToDumpedFilesDict(dumpedFilesList):
  dumpedFilesDict = {}
  for dumpedFilesInstance in dumpedFilesList:
    if dumpedFilesInstance['hostName'] not in dumpedFilesDict:
      dumpedFilesDict[dumpedFilesInstance['hostName']] = {}
    if dumpedFilesInstance['backupFilesystem'] not in dumpedFilesDict[dumpedFilesInstance['hostName']]:
      dumpedFilesDict[dumpedFilesInstance['hostName']][dumpedFilesInstance['backupFilesystem']] = []
    dumpedFilesDict[dumpedFilesInstance['hostName']][dumpedFilesInstance['backupFilesystem']].append(
      ( dumpedFilesInstance['dumpLevel'], dumpedFilesInstance['mtime'], dumpedFilesInstance['path'] )
    )
  print(json.dumps(dumpedFilesDict, indent=2))
  return dumpedFilesDict

def removeOldDumpedFiles(dumpedFilesDict):
  dayLength = ( 60 ** 2 ) * 24
  removalList = []
  for dumpedOnHostname, dumpedFileSystemDict in dumpedFilesDict.items():
    for dumpedFileSystem, dumpsList in dumpedFileSystemDict.items():
      dumpLevelDict = {}
      for dumpInstance in dumpsList:
        print(dumpedOnHostname, dumpedFileSystem, dumpInstance)
        dumpLevelDict[ dumpInstance[0] ] = dumpInstance
      dumpLevelList = list(dumpLevelDict.keys())
      # From here on dump level list is sorted.
      dumpLevelList.sort()
      # Initalize modification time.
      olderValue = 0
      # Dont remove everything yet.
      removeAll = False
      # Now will look for files to remove.
      for dumpLevelInstance in dumpLevelList:
        # In case we remove everything, just do it and go on.
        if removeAll:
          removalList.append(dumpLevelDict[dumpLevelInstance][2])
          continue
        # Find out the modification time of current file.
        currentInstanceMtime = dumpLevelDict[dumpLevelInstance][1]
        # In case the current file is newer, do something,
        # otherwise remove everything.
        if olderValue < currentInstanceMtime:
          if dumpLevelInstance > 8:
            removeAll = True
            removalList.append(dumpLevelDict[dumpLevelInstance][2])
            continue
          # Only do something if dump level is more than zero.
          if dumpLevelInstance > 0:
            # difference between currentMtime and formerMtime
            currentMtimeDiff = currentInstanceMtime - olderValue
            # is higher than difference set as treshold.
            tresholdDiff = dayLength * ( 10 - dumpLevelInstance )
            if currentMtimeDiff > tresholdDiff:
              removeAll = True
              removalList.append(dumpLevelDict[dumpLevelInstance][2])
          # Set older value to current file modification time.
          olderValue = currentInstanceMtime
          continue
        removeAll = True
        removalList.append(dumpLevelDict[dumpLevelInstance][2])
  print("Will remove following file paths:")
  print(json.dumps(removalList, indent=2))

def analyzeDumpFileName(dumpFileName):
  dumpFileNamePartList = dumpFileName.rpartition(".")[0].split("_")
  analyzedDumpFile = {}
  analyzedDumpFile['hostName'] = dumpFileNamePartList[0]
  analyzedDumpFile['backupFilesystem'] = dumpFileNamePartList[1]
  analyzedDumpFile['dumpLevel'] = int(dumpFileNamePartList[2])
  return analyzedDumpFile

def createDumpFileName(hostName, backupFilesystem, backupDir):
  backupFilesystemPart = backupFilesystem.replace("-","")
  backupFilesystemPart = backupFilesystemPart.replace("_","")
  backupFilesystemPartList = backupFilesystemPart.split("/")
  backupFilesystemPartList.pop(0)
  backupFilesystemPart = str.join("-", backupFilesystemPartList)
  for dumpLevel in range(0, 10):
    dumpFileName = str.join("_", [ hostName, backupFilesystemPart, str(dumpLevel) ]) + ".xfsdump"
    if not os.path.exists(str.join("/", [ backupDir, dumpFileName])):
      break
  return dumpFileName

def createDumpFileNameList(config):
  dumpFileNameList = []
  hostName = config["HostName"]
  backupDir = config["BackupDir"]
  backupFilesystemList = config["BackupFilesystems"]
  for backupFilesystem in backupFilesystemList:
    dumpFileNameList.append( createDumpFileName(hostName, backupFilesystem, backupDir) )
  return dumpFileNameList

def isPathXfsFilesystem(backupFilesystemCandidate):
  with subprocess.Popen(["mount", "-vv"], stdout=subprocess.PIPE, universal_newlines=True) as showMountsProcess:
    for showMountsProcessLine in showMountsProcess.stdout.read().split("\n"):
      showMountsProcessLineList = showMountsProcessLine.split()
      filesystemType = showMountsProcessLineList.pop(4)
      mountPath = showMountsProcessLineList.pop(2)
      if filesystemType == "xfs":
        if mountPath == backupFilesystemCandidate:
          print("SUCCESS: Backup filesystem candidate confirmed:", backupFilesystemCandidate)
          return True
  print("ERROR: Backup filesystem candidate not found in the mount list:", backupFilesystemCandidate)
  return False

if __name__ == "__main__":
  cmdLineArgs = sys.argv
  ownPath = cmdLineArgs.pop(0)
  verbose = False
  doConfig = False
  if "-v" in cmdLineArgs:
    verbose = True
    cmdLineArgs.pop( cmdLineArgs.index("-v") )
  if "-c" in cmdLineArgs:
    doConfig = True
    cmdLineArgs.pop( cmdLineArgs.index("-c") )
  config = {}
  configFilePath = str.join("/", [ os.path.dirname(ownPath), 'config.dbm' ])
  if verbose:
    print("Opening configuration file:", configFilePath)
  configFile = dbm.open(configFilePath, 'c')
  if doConfig:
    backupDir = input("Configure a backup directory:")
    if not os.path.isdir(backupDir):
      print("ERROR: Configured backup directory does not exist. Quitting!")
      sys.exit(1)
    configFile["backupDir"] = backupDir.encode()
    configFile["hostName"] = socket.gethostname().split('.').pop(0).encode()
    backupFilesystems = []
    while len(cmdLineArgs) > 0:
      backupFilesystemCandidate = cmdLineArgs.pop()
      if isPathXfsFilesystem(backupFilesystemCandidate):
        backupFilesystems.append(backupFilesystemCandidate)
    configFile["backupFilesystems"] = json.dumps(backupFilesystems)
  if ( b'backupDir' in configFile.keys() and b'hostName' in configFile.keys()
      and b'backupFilesystems' in configFile.keys() ):
    config["BackupDir"] = configFile["backupDir"].decode()
    config["HostName"] = configFile["hostName"].decode()
    config["BackupFilesystems"] = json.loads(configFile["backupFilesystems"])
  else:
    if verbose:
      print("Config file keys include:", configFile.keys())
    print("ERROR: Configuration file seems to be empty, configure first with \"-c\". Quitting!")
    sys.exit(1)
  if verbose:
    print("SUCCESS: Running with configuration:")
    print(json.dumps(config,indent=2))
  removeOldDumpedFiles(
    convertToDumpedFilesDict(
      analyzeDumpDir(config["BackupDir"])
    )
  )
  dumpFileNameList = createDumpFileNameList(config)
  if verbose:
    print(json.dumps(dumpFileNameList, indent=2))
  for dumpFileNameInstance in dumpFileNameList:
    doFileSystemBackup(config, dumpFileNameInstance)