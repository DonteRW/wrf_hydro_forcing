"""Regrid_Driver
Checks data directories for new content, and if 
found initiates regrid/rescaling python scripts.
Keeps state in a state file that is read/written
each time this script is invoked.  The state
file contains the most recent data files.
Logs to a log file that is created in the
same directory from where this script is executed.  
"""

import os
import sys
import logging
import datetime
import time
from ConfigParser import SafeConfigParser
import DataFiles as df
import WhfLog
import Short_Range_Forcing as srf
import Analysis_Assimilation_Forcing as aaf
import Medium_Range_Forcing as mrf
from ForcingEngineError import FilenameMatchError
from ForcingEngineError import InvalidArgumentError
from ForcingEngineError import SystemCommandError
from ForcingEngineError import ZeroHourReplacementError

#----------------------------------------------------------------------------
def parmRead(fname, fileType):
   """Read in the main config file, return needed parameters

   Parameters
   ----------
   fname: str
      name of parameter file to read in
   fileType: str
      'RAP', 'HRRR', 'MRMS', 'GFS'

   Returns
   -------
   Parms
      values as pulled from the file

   """
    
   parser = SafeConfigParser()
   parser.read(fname)

   forcing_config_label = "Regrid" + fileType

   if (fileType == 'HRRR'):
      configType = 'Short'
   elif (fileType == 'RAP'):
      configType = 'Short'
   elif (fileType == 'GFS'):
      configType = 'Medium'
   elif (fileType == 'MRMS'):
      configType = 'AA'
   else:
      configType = '???'

   WhfLog.init(parser, forcing_config_label, configType, 'Regrid', fileType)
      
   dataDir = parser.get('data_dir', fileType + '_data')
   maxFcstHour = int(parser.get('fcsthr_max', fileType + '_fcsthr_max'))
   hoursBack = int(parser.get('triggering', fileType + '_hours_back'))
   stateFile = parser.get('triggering', fileType + '_regrid_state_file')
   
   parms = Parms(dataDir, maxFcstHour, hoursBack, stateFile)
   return parms

#----------------------------------------------------------------------------
def regridIfZeroHr(configFile, fileType, fname):
   """If it is a 0 hour forecast (RAP or HRRR) regrid in a special way
   Parameters
   ----------
   configFile : str
   configuration file with all settings
   fileType: str
   HRRR, RAP, ... string
   fname: str
   name of file to regrid and downscale, with yyyymmdd parent dir

   Returns
   -------
   None
   """
   # check for 0 hour by creating a DataFile and checking forecast hour
   try:
      f = df.DataFile(fname[0:8], fname[9:], fileType)
   except FilenameMatchError as fe:
      WhfLog.debug("Cannot check for 0 hour data due to %s", fe)
      raise
   except InvalidArgumentError as ie:
      WhfLog.debug("Cannot check for 0 hour data due to %s", ie)
      raise
   if (f._time._forecastHour == 0):
      WhfLog.setConfigType('AA')
      WhfLog.debug("SPECIAL 0 hour case %s", fname[9:0])
      aaf.forcing(configFile, 'regrid', fileType, fname[9:])
      WhfLog.setConfigType('Short')

#----------------------------------------------------------------------------
def regrid(fname, fileType, configFile):
   """Invoke regridding/downscaling 
       
   Parameters
   ----------
   fname: str
      name of file to regrid and downscale, with yyyymmdd parent dir
   fileType: str
      HRRR, RAP, ... string
   configFile : str
      configuration file with all settings

   Returns
   -------
   None

   """

   WhfLog.info("REGRIDDING %s DATA, file=%s", fileType, fname)
   try:
      if (fileType == 'HRRR'):
         srf.forcing(configFile, 'regrid', 'HRRR', fname[9:])
         # special case, if it is a 0 hour forecast, do double regrid
         regridIfZeroHr(configFile, fileType, fname)
      elif (fileType == 'RAP'):
         srf.forcing(configFile, 'regrid', 'RAP', fname[9:])
         # special case, if it is a 0 hour forecast, do double regrid
         regridIfZeroHr(configFile, fileType, fname)
      elif (fileType == 'GFS'):
         mrf.forcing(configFile, 'regrid', 'GFS', fname[9:])
      elif (fileType == 'MRMS'):
         aaf.forcing(configFile, 'regrid', 'MRMS', fname[9:])
      else:
         WhfLog.info("ERROR REGRIDDING %s DATA, file=%s", fileType, fname)
         raise InvalidArgumentError("Unknown file type " + fileType)
   except ZeroHourReplacementError as z:
      WhfLog.info("ERROR REGRIDDING: %s", z)
      WhfLog.info("Remove this forecast from list of to do forecasts")
   except:
      WhfLog.info("ERROR REGRIDDING %s DATA, file=%s", fileType, fname)
      raise

   WhfLog.info("DONE REGRIDDING %s DATA, file=%s", fileType, fname)
    
#----------------------------------------------------------------------------
class Parms:
   """Parameters from the main wrf_hydro param file that are needed 

   Attributes
   ----------
   _dataDir: str
      Topdir for data
   _maxFcstHour: int
      Maximum forecast hour to process
   _hoursBack: int
      Hours back to maintain state
   _stateFile: str
      Name of file with state information that is read/written
   """

   def __init__(self, dataDir, maxFcstHour, hoursBack, stateFile):
      """Initialization using input args

      Parameters
      ----------
      One to one with attributes, self explanatory
      """
      self._dataDir = dataDir
      self._maxFcstHour = maxFcstHour
      self._hoursBack = hoursBack
      self._stateFile = stateFile

   def debugPrint(self):
      """ Debug logging of content
      """
      WhfLog.debug("Parms: data = %s", self._dataDir)
      WhfLog.debug("Parms: MaxFcstHour = %d", self._maxFcstHour)
      WhfLog.debug("Parms: StateFile = %s", self._stateFile)


#----------------------------------------------------------------------------

# Internal state that is read in and saved out
# The state
#
class State:
   """Internal state that is read in and saved out

   Attributes
   ----------
   _empty: bool
      True if state is not set
   _data
      data file names with yyyymmdd parent directory
   """

   def __init__(self, parmFile="", fileType=""):
      """Initialize using parameters read in from a file

      Parameters
      ----------
      parmFile: str
         Name of param file to read
      fileType: str
         'HRRR', 'RAP', ...
      """

      if (not parmFile):
         self._empty = True
         self._data = []
      else:
         self._empty = False
         cf = SafeConfigParser()
         cf.read(parmFile)
         self._data = [name for name in cf.get("latest", fileType).split()]

   def isEmpty(self):
      """Check if state is set or not

      Parameters
      ----------
         none
    
      Returns
      -------
         true if state is not set
      """
      if (self._empty):
         return True
      return (not self._data)

   def newest(self):
      """return newest file

      Returns
      -------
      str
         File name (newest), or empty string if none
         
      """
      if (self.isEmpty()):
         return ""
      return (self._data[-1])
      

   def initialize(self, data, fileType):
      """Initialize from DataFiles inputs

      Parameters
      ----------
      data: DataFiles
         data
      fileType : str
         'HRRR', etc
    
      Returns
      -------
         None
      """
      self._empty = False
      self._data = data.getFnames()

   def debugPrint(self):
      """ logging debug of contents
      """
      for f in self._data:
         WhfLog.debug("State:%s", f)
        
   def update(self, time, hoursBack, fileType):
      """Update typed state so that input time is newest one

       Parameters
       ----------
       time: ForecastTime
          The newest time
       hoursBack:
          Maximum issue time hours back compared to time
       fileType: str
          'HRRR', ...
       
       Returns
       -------
       none
       """
      self._data = df.filterWithinNHours(self._data, fileType, time, hoursBack)
      
   def isNew(self, f):
      return (not f in self._data)

   def addFileIfNew(self, f):
      """ If input file is not in state, add it

      Parameters
      ----------
      f:str
         File name

      Returns
      -------
      bool
         True if added, false if already in the state

      """
      ret = False
      if (not f in self._data):
          self._data.append(f)
          ret = True
      return ret
   
   def sortFiles(self):
      """ Sort the files into ascending order for a type

      Note: sort depends on naming being 'nice'

      Returns
      -------
      none

      """
      self._data.sort()

   def lookForNew(self, data, hoursBack, fileType):
      """ See if new data has arrived compared to state.
      If a new issue time, purge older stuff from state.

      Parameters
      ----------
      data: DataFiles
         The newest data
      hoursBack: int
         Maximum number of hours back to keep data in state
      fileType : str
         'HRRR', 'RAP', ...
      Returns
      -------
      list[str]
          The data file names that are are to be added to state
      """
         
      ret = []
      fnames = data.getFnames()
      if (not fnames):
         return ret

      if (self.isEmpty()):
         WhfLog.debug("Adding to empty list")
      else:
         sname = self.newest()
         if (not sname):
            WhfLog.error("Expected file, got none")
            return ret
         if (fnames[-1] > sname):
            WhfLog.debug("Newer time encountered")
            # see if issue time has increased and if so, purge old stuff
            # create DataFile objects, which requires breaking the full
            # file into yymmdd/filename
            sind = sname.find('/')
            if (sind < 0):
               raise FileNameMatchError('Cannot parse directory from ' + sname)
            nind = fnames[-1].find('/')
            if (sind < 0):
               raise FileNameMatchError('Cannot parse directory from ' + fnames[-1])

            symd = sname[:sind]
            sfile = sname[sind+1:]
            nymd = fnames[-1][:nind]
            nfile = fnames[-1][nind+1:]
            WhfLog.debug("Checking %s / %s  against %s / %s", symd, sfile, nymd, nfile)
            try:
               df0 = df.DataFile(symd, sfile, fileType)
               df1 = df.DataFile(nymd, nfile, fileType)
            except FilenameMatchError as fe:
               WhfLog.debug("Cannot update due to %s", fe)
            except InvalidArgumentError as ie:
               WhfLog.debug("Cannot update due to %s", ie)

            if (df0._time.inputIsNewerIssueHour(df1._time)):
               WhfLog.debug("%s Issue hour has increased, purge now",
                            fileType)
               self.update(df1._time, hoursBack, fileType)

      for f in fnames:
         if (self.isNew(f)):
            ret.append(f)
      return ret


   def updateWithNew(self, data, hoursBack, fileType):
      """ Update internal state with new data

      Parameters
      ----------
      data: DataFiles
         The newest data
      hoursBack: int
         Maximum number of hours back to keep data in state
      fileType : str
         'HRRR', 'RAP', ...
      Returns
      -------
      list[str]
          The data file names that are are newly added to state
      """
         
      ret = []
      fnames = data.getFnames()
      if (not fnames):
         return ret

      if (self.isEmpty()):
         WhfLog.debug("Adding to empty list")
      else:
         sname = self.newest()
         if (not sname):
            WhfLog.error("Expected file, got none")
            return ret
         if (fnames[-1] > sname):
            WhfLog.debug("Newer time encountered")
            # see if issue time has increased and if so, purge old stuff
            # create DataFile objects
            try:
               df0 = df.DataFile(sname[0:8], sname[9:], fileType)
               df1 = df.DataFile(fnames[-1][0:8], fnames[-1][9:], fileType)
            except FilenameMatchError as fe:
               WhfLog.debug("Cannot update due to %s", fe)
            except InvalidArgumentError as ie:
               WhfLog.debug("Cannot update due to %s", ie)

            if (df0._time.inputIsNewerIssueHour(df1._time)):
               WhfLog.debug("%s Issue hour has increased, purge now",
                            fileType)
               self.update(df1._time, hoursBack, fileType)

      for f in fnames:
         if (self.addFileIfNew(f)):
            ret.append(f)

      self.sortFiles()
      return ret
        
   def write(self, parmFile, fileType):
      """ Write state to param file

      Parameters
      ----------
      parmFile: Name of file to write to 
      fileType: str
          'HRRR', etc
            
      Returns
      -------
      None
      """
         
      config = SafeConfigParser()

      # When adding sections or items, add them in the reverse order of
      # how you want them to be displayed in the actual file.
      # In addition, please note that using RawConfigParser's and the raw
      # mode of ConfigParser's respective set functions, you can assign
      # non-string values to keys internally, but will receive an error
      # when attempting to write to a file or when you get it in non-raw
      # mode. SafeConfigParser does not allow such assignments to take place.

      config.add_section('latest')

      s = ""
      for f in self._data:
         s += f
         s += "\n"
      config.set('latest', fileType, s)

      # Write it out
      with open(parmFile, 'wb') as configfile:
         config.write(configfile)

#----------------------------------------------------------------------------
def createStateFile(parms, fileType):
   """  Called if there is no state file, look at data dirs and create state

   Parameters
   ----------
   parms: Parms
      Parameter settings
   fileType: str
      'HRRR', ...

   Returns
   -------
   none

   Writes out the state file after creating it
   """

   WhfLog.info("Initializing")


   # query each directory and get newest model run file for each, then
   # get all for that and previous issue time
   data = df.DataFiles(parms._dataDir, parms._maxFcstHour, fileType)
   data.setNewestFiles(parms._hoursBack)
   for f in data._content:
      f.debugPrint("Newest files: " + fileType)

   state = State("")
   state.initialize(data, fileType)

   # maybe back up  and regrid that entire issue time
   # maybe redo this exact set of inputs only
   # maybe do nothing
   # maybe do all of them..for now do nothing as its easiest, just move on

   # write out file (at least try to)
   state.write(parms._stateFile, fileType)

#----------------------------------------------------------------------------
def main(argv):

    fileType = argv[0]
    good = False
    if (fileType == 'HRRR' or fileType == 'RAP' or fileType == 'MRMS' or
        fileType == 'GFS'):
       good = True
    if (not good):
       print 'ERROR unknown file type command arg ', fileType
       return 1

    # User must pass the config file into the main driver.
    configFile = argv[1]
    if not os.path.exists(configFile):
        print 'ERROR forcing engine config file not found:', configFile
        return 1
    
    # read in fixed main params
    parms = parmRead(configFile, fileType)

    #parms.debugPrint()

    #if there is not a state file, create one now using newest
    if (not os.path.exists(parms._stateFile)):
        parms.debugPrint()
        createStateFile(parms, fileType)
        
    # begin normal processing situation
    #WhfLog.debug("....Check for new input data to regid")
    
    # read in state
    state = State(parms._stateFile, fileType)
    
    # query each directory and get newest model run file for each, then
    # get all for that and previous issue time
    data = df.DataFiles(parms._dataDir, parms._maxFcstHour, fileType)
    data.setNewestFiles(parms._hoursBack)

    # Update the state to reflect changes, returning those files to regrid
    # Regrid 'em
    toProcess = state.lookForNew(data, parms._hoursBack, fileType)
    for f in toProcess:
       try:
          regrid(f, fileType, configFile);
       except:
          WhfLog.error("Could not regrid/downscale %s", f)
       else:
          WhfLog.debug("Adding new file %s, and writing state file", f)
          if (not state.addFileIfNew(f)):
             WhfLog.error("File %s was not new", f)
          else:
             state.write(parms._stateFile, fileType);
          
    # write out state (in case it has not been written yet) and exit
    #state.debugPrint()
    state.write(parms._stateFile, fileType)
    return 0

#----------------------------------------------

if __name__ == "__main__":
    main(sys.argv[1:])
