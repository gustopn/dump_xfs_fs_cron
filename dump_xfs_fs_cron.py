#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import dbm
import json
import socket

def doFileSystemBackup(config, dumpFileName):
  dumpFilePath = str.join("/", [ config['BackupDir'], dumpFileName ])
  dumpFileDict = analyzeDumpFileName(dumpFileName)
  dumpFileLevel = dumpFileDict['dumpLevel']
  dumpFileSystem = str.join("/", ( [ "" ] + dumpFileDict['backupFilesystem'] ) )
  xfsdumpCommand = [ "sudo", "xfsdump", "-F", "-f", dumpFilePath, "-l", str(dumpFileLevel), dumpFileSystem ]
  print("Will execute following command:")
  print(xfsdumpCommand)

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
        dumpLevelList[ dumpInstance[0] ] = dumpInstance
      dumpLevelList = dumpLevelDict.keys()
      dumpLevelList.sort()
      olderValue = 0
      removeAll = False
      for dumpLevelInstance in dumpLevelList:
        if removeAll:
          removalList.append(dumpLevelDict[dumpLevelInstance][2])
          continue
        currentInstanceMtime = dumpLevelDict[dumpLevelInstance][1]
        if olderValue < currentInstanceMtime:
          if dumpLevelInstance > 0:
            if ( currentInstanceMtime - olderValue ) > ( dayLength * dumpLevelInstance * 2 ):
              removeAll = True
              removalList.append(dumpLevelDict[dumpLevelInstance][2])
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
  analyzedDumpFile['backupFilesystem'] = dumpFileNamePartList[1].split("-")
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