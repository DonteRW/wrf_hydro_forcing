""" ShortRangeLayeringDriver.py
Checks regrid/rescale data directories for new content, and if 
found and time to do so, initiate layering scripts.
Keeps state in a state file that is read/written
each time this script is invoked.  The state
file shows the most recent issue times status as regards inputs and layering.
Logs to a log file that is created in the
same directory from where this script is executed.  
"""

import os
import sys
import WhfLog
import datetime
import time
from ConfigParser import SafeConfigParser
import Short_Range_Forcing as srf
import DataFiles as df
import WhfLog

#----------------------------------------------------------------------------
def parmRead(fname):
    """ Read in a param file

    Parameters
    ---------
    fname : str
       Name of the file to read
    Returns
    -------
    Parms
        The parameters that were read in
    """

    parser = SafeConfigParser()
    parser.read(fname)

    forcing_config_label = "ShortRangeLayeringDriver"
    WhfLog.init(parser, forcing_config_label, 'Short', 'Layer', 'RAP/HRRR')

    hrrrDir = parser.get('downscaling', 'HRRR_finished_output_dir')
    #mrmsDir = parser.get('data_dir', 'MRMS_data')
    rapDir = parser.get('downscaling', 'RAP_finished_output_dir')
    layerDir = parser.get('layering', 'short_range_output')
    maxFcstHour = int(parser.get('fcsthr_max', 'HRRR_fcsthr_max'))

    # go with HRRR
    hoursBack = int(parser.get('triggering', 'HRRR_hours_back'))

    maxWaitMinutes=int(parser.get('triggering',
                                  'short_range_fcst_max_wait_minutes'))
    veryLateMinutes=int(parser.get('triggering',
                                   'short_range_fcst_very_late_minutes'))
    stateFile = parser.get('triggering', 'short_range_layering_state_file')

    parms = Parms(hrrrDir, rapDir, layerDir, maxFcstHour, hoursBack,
                  maxWaitMinutes, veryLateMinutes, stateFile)

    return parms

#----------------------------------------------------------------------------
class Parms:
    """ Parameters from the main wrf_hydro param file that are used for layering

    Attributes
    ----------
    _hrrrDir : str
       HRRR top input directory
    _rapDir : str
       RAP top input directory
    _layerDir : str
       output top directory
    _maxFcstHour : int
       maximum forecast hour for layered output
    _hoursBack : int
       Hours back to maintain state, issue time
    _maxWaitSeconds
       Maximum number of sec. to wait for additional inputs after first arrives
    _veryLateSeconds
       Maximum number of sec. before declaring a forecast very late
    _stateFile : str
        Name of file with state information
    """
    def __init__(self, hrrrDir, rapDir, layerDir, maxFcstHour, hoursBack,
                 maxWaitMinutes, veryLateMinutes, stateFile) :
        """ Initialize from input args
        
        Attributes
        ----------
        hrrrDir : str
            HRRR top input directory
        rapDir : str
            RAP top input directory
        layerDir : str
            output top directory
        maxFcstHour : int
            maximum forecast hour for layered output
        hoursBack: int
            hours back to maintain state
        maxWaitMinutes:
            minutes to wait for completion of a forecast
        veryLateMinutes:
            when to complain a forecast is late
        stateFile : str
            Name of file with state information
        """
        self._hrrrDir = hrrrDir
        self._rapDir = rapDir
        self._layerDir = layerDir
        self._maxFcstHour = maxFcstHour
        self._hoursBack = hoursBack
        self._maxWaitSeconds = maxWaitMinutes*60
        self._veryLateSeconds = veryLateMinutes*60
        self._stateFile = stateFile


    def debugPrint(self):
        """ WhfLog debug of content
        """
        WhfLog.debug("Parms: HRRR_data = %s", self._hrrrDir)
        WhfLog.debug("Parms: RAP_data = %s", self._rapDir)
        WhfLog.debug("Parms: Layer_data = %s", self._layerDir)
        WhfLog.debug("Parms: MaxFcstHour = %d", self._maxFcstHour)
        WhfLog.debug("Parms: HoursBack = %d", self._hoursBack)
        WhfLog.debug("Parms: maxWaitSeconds = %d", self._maxWaitSeconds)
        WhfLog.debug("Parms: veryLateSeconds = %d", self._veryLateSeconds)
        WhfLog.debug("Parms: StateFile = %s", self._stateFile)


#----------------------------------------------------------------------------
class ForecastStatus:
    """ Internal state that is read in and saved out, individual forecast

    Attributes

    _empty : bool
       true if contents not set
    _issue : datetime
       Issue time (y, m, d, h, 0, 0)
    _valid : datetime
       Valid time (y, m, d, h, 0, 0)
    _hrrr : bool
       true if HRRR input is available
    _rap : bool
       true if RAP input is available
    _layered : bool
       true if this forecast has been layered
    _clockTime : datetime
       time at which the first forecast input was available
    """
    def __init__(self, configString=""):
        """ Initialize by parsing a a config file  line

        Parameters
        ----------
        configString : str
           Config file line, or empty
        """

        # init to empty
        self._empty = 1
        self._issue = datetime.datetime
        self._valid = datetime.datetime
        self._hrrr = 0
        self._rap = 0
        self._layered = 0
        self._clockTime = datetime.datetime
        if not configString:
            return

        # parse
        self._empty = 0
        self._issue=datetime.datetime.strptime(configString[0:10], "%Y%m%d%H")
        self._valid=datetime.datetime.strptime(configString[11:23],
                                              "%Y%m%d%H%M")
        self._hrrr=int(configString[24:25])
        self._rap=int(configString[26:27])
        self._layered=int(configString[28:29])
        self._clockTime = datetime.datetime.strptime(configString[30:],
                                                     "%Y-%m-%d_%H:%M:%S")

    def debugPrint(self):
        """ WhfLog debug of content
        """
        WhfLog.debug("Fcst: empty=%d", self._empty)
        if (self._empty):
            return
        WhfLog.debug("Fcst: I:%s V:%s hrrr:%d rap:%d layered:%d clockTime=%s",
                      self._issue.strftime("%Y%m%d%H"),
                      self._valid.strftime("%Y%m%d%H"), self._hrrr, self._rap,
                      self._layered, 
                      self._clockTime.strftime("%Y-%m-%d_%H:%M:%S"))

    def setContent(self, issueTime, lt):
        """ Set content using inputs

        Parameters
        ----------
        issueTime : datetime
            Model run time
        lt : int
            Forecast time seconds
        """
        self._empty = 0
        self._issue = issueTime
        self._valid = issueTime + datetime.timedelta(minutes=lt*60)
        self._hrrr = 0
        self._rap = 0
        self._layered = 0
        self._clockTime = datetime.datetime.utcnow()
        
    def notTooOld(self, itime, hoursBack):
        """ check if local issue time is not too old compared to input time

        Parameters
        ----------
        itime : datetime
            Time to check against
        hoursBack  : maximum issue time hours earlier for local time

        Returns
        -------
        bool
            True if _issue >= itime - hoursBack
        """
        if (self._empty == 1):
            return 0
        else:
            return self._issue >= itime - datetime.timedelta(hours=hoursBack)

    def writeConfigString(self):
        """ Write local content as a one line string
        Returns
        -------
        str
        """
        if (self._empty):
            # write fake stuff out
            ret = "2015010100,201501010000,0,0,0,2015-01-01_00:00:00"
        else:
            ret = self._issue.strftime("%Y%m%d%H") + ","
            ret += self._valid.strftime("%Y%m%d%H%M")
            ret += ',%d,%d,%d,' %(self._hrrr, self._rap, self._layered)
            ret += self._clockTime.strftime("%Y-%m-%d_%H:%M:%S")
        return ret
    
    def matches(self, model):
        """ Check if input has same issue time as local

        Parameters
        ----------
        model: Model
           model specification, with issue time

        Returns
        -------
        bool
           True if input issue = local issue
        """
        return self._issue == model._issue

    def setCurrentModelAvailability(self, parms, model):
        """ Change availability status when appropriate by looking at disk

        Parameters
        ----------
        parms : Parms
            parameters
        model : Model
            overall status for this model run, used for clock time

        Returns
        -------
        none
        """

        if (self._layered):
            # no need to do more, already layered
            return
        
        # make note if going from nothing to something
        nothing = (self._hrrr == 0 and self._rap == 0)

        #if (nothing):
            #WhfLog.debug("Nothing, so trying to get stuff")
        if (self._hrrr == 0):
            # update HRRR status
            self._hrrr = self.forecastExists(parms._hrrrDir)
        if (self._rap == 0):
            # update RAP status
            self._rap = self.forecastExists(parms._rapDir)
        if (nothing and (self._hrrr == 1 or self._rap == 1)):
            # went from nothing to something, so start the clock
            WhfLog.debug("Starting clock now, hrrr=%d, rap=%d", self._hrrr,
                          self._rap)
            self._clockTime = datetime.datetime.utcnow()
        else:
            if (nothing and (self._hrrr == 0 and self._rap == 0)):
                # nothing to nothing, compare current time to time from
                # model input, and squeaky wheel if too long
                tnow = datetime.datetime.utcnow()
                diff = tnow - model._clockTime 
                idiff = diff.total_seconds()
                if (idiff > parms._veryLateSeconds):
                    WhfLog.warning("Inputs for short range layering are very late Issue:%s Valid:%s",
                                  self._issue.strftime("%Y%m%d%H"),
                                  self._valid.strftime("%Y%m%d%H"))
    def forecastExists(self, dir):
        """ Check if forecast indicated by local state exists

        Parameters
        ----------
        dir : str
           Full path to the issue time directories

        Returns
        -------
        bool
           True if the forecast does exist on disk
        """
           
        path = dir + "/"
        path += self._issue.strftime("%Y%m%d%H")
        if (os.path.isdir(path)):
            fname = self._valid.strftime("%Y%m%d%H%M") + ".LDASIN_DOMAIN1.nc"
            names = df.getFileNames(path)
            for n in names:
                if (n == fname):
                    WhfLog.debug("Found %s in %s",  fname, path)
                    return 1
            return 0
        else:
            return 0

    def layerIfReady(self, parms, configFile):
        """  Perform layering if state is such that it should be done

        Parameters
        ----------
        parms : Parms
           Parameters
        configFile : string
           name of file with settings

        Returns
        -------
        bool
           True if layering was done, or had previously been done
        """
        
        if (self._layered == 1):
            return 1
        if (self._hrrr == 0 and self._rap == 0):
            return 0
        if (self._hrrr == 1 and self._rap == 1):
            self.layer(parms, configFile)
            self._layered = 1
            return 1
        if (self._hrrr == 0 and self._rap == 1):
            ntime = datetime.datetime.utcnow()
            diff = ntime - self._clockTime
            idiff = diff.total_seconds()
            if (idiff > parms._maxWaitSeconds):
                WhfLog.debug("timeout..Should layer, dt=%d", idiff)
                self.passthroughRap(parms)
                self._layered = 1
                return 1
        return 0
            
    def layer(self, parms, configFile):
        """ Perform layering

        NOTE: here is where returns status will be added and used
        
        Parameters
        ----------
        parms : Parms
          parameters
        configFile : string
          name of file with settings

        """        
        path = self._issue.strftime("%Y%m%d%H") + "/"
        path += self._valid.strftime("%Y%m%d%H%M") + ".LDASIN_DOMAIN1.nc"
        WhfLog.info("LAYERING %s ", path)
        srf.forcing(configFile, 'layer', 'HRRR', path, 'RAP', path)
        WhfLog.info("DONE LAYERING file=%s", path)

    def passthroughRap(self, parms):
        """ Perform pass through of RAP data as if it were layered

        NOTE: Add some error status catching for return
        
        Parameters
        ----------
        parms : Parms
          parameters

        """        

        # lots of hardwires here
        ymdh = self._issue.strftime("%Y%m%d%H")
        path = ymdh + "/"
        fname = self._valid.strftime("%Y%m%d%H%M") + ".LDASIN_DOMAIN1.nc"
        fnameOut = self._valid.strftime("%Y%m%d%H%M") + ".LDASIN_DOMAIN1"
        path += fname
        WhfLog.setData('RAP')
        WhfLog.info("LAYERING (Passthrough) %s ", path)

        # if not there, create the directory to put the file into
        fullPath = parms._layerDir + "/"
        fullPath += ymdh
        if not os.path.exists(fullPath):
            os.makedirs(fullPath)

        if not os.path.isdir(fullPath):
            WhfLog.error("%s is not a directory", fullPath)
        else:
            # create copy command and do it
            cmd = "cp " + parms._rapDir
            cmd += "/" + path
            cmd += " " + fullPath
            cmd += "/"
            cmd += fnameOut
            WhfLog.info(cmd)
            os.system(cmd)

        WhfLog.info("LAYERING (Passthrough) %s complete", path)
        WhfLog.setData('RAP/HRRR')
            
            
#----------------------------------------------------------------------------
class Model:
    """ Specs for an entire model run

    Attributes
    -----------
    _empty : bool
       True if object has not content
    _issue : datetime
       Model issue time  (y,m,d,h)
    _clockTime : datetime
       Real time at which the initial forecast was available
    """

    def __init__(self, configString=""):
        """ Initialize by parsing a config file line

        Parameters
        ----------
        configString : str
            The line to parse, or empty
        """

        if (not configString):
            # set empty values
            self._empty = 1
            self._issue = datetime.datetime
            self._clockTime = datetime.datetime
        else:
            # parse
            self._empty = 0
            self._issue = datetime.datetime.strptime(configString[0:10],
                                                    "%Y%m%d%H")
            self._clockTime = datetime.datetime.strptime(configString[11:],
                                                    "%Y-%m-%d_%H:%M:%S")
    def debugPrint(self):
        """ WhfLog debug of content
        """
        WhfLog.debug("Model: empty=%d", self._empty)
        if (self._empty):
            return
        WhfLog.debug("Model: Issue=%s  clockTime=%s",
                      self._issue.strftime("%Y%m%d%H"),
                      self._clockTime.strftime("%Y-%m-%d_%H:%M:%S"))
        
                      
    def setContent(self, issueTime):
        """ set content using input, set clocktime to real time

        Parameters
        ----------
        issueTime : datetime
           The issue time to use
        """
        self._empty = 0
        self._issue = issueTime
        self._clockTime = datetime.datetime.utcnow()

    def writeConfigString(self):
        """ Write contents as a config file string line

        Returns
        -------
        str
           The string representation of state
        """
        if (self._empty == 1):
            # fake return, with correct format
            ret = "2015010100,2015-01-01_00:00:00"
        else:
            # write it out
            ret = self._issue.strftime("%Y%m%d%H") + ","
            ret += self._clockTime.strftime("%Y-%m-%d_%H:%M:%S")
        return ret
    
    def inputIssueTimeEqual(self, itime):
        """ Check if issue time passed in is same as local
        Parameters
        ----------
        itime : datetime
        Returns
        -------
        bool
           true if same
        """
        if (self._empty == 1):
            return 0
        else:
            return itime == self._issue
        
    def notTooOld(self, itime, hoursBack):
        """ Check if local issuetime is not too old compared to input issuetime

        Parameters
        ----------
        itime : datetime
           The issue time
        hoursBack : int
           Maximum issue time hours back for local

        Returns
        -------
        bool
           True if _itime >= itime - hoursBack 
        """
        if (self._empty == 1):
            return 0
        else:
            return self._issue >= itime - datetime.timedelta(hours=hoursBack)
        

#----------------------------------------------------------------------------
class State:
    """ Internal state that is read in and written out to a state file

    Attributes
    ----------
    _empty : bool
       true if state is not set
    _model : list[Model]
       the model runs that are active
    _fState : list[ForecastStatus]
       the individual forecasts that are active

    """
    def __init__(self):
        """ Initialize to empty
        """
        self._empty = 1
        self._model = []
        self._fState = []

    def initFromStateFile(self, parmFile):
        """ Initialize from the sate file, by parsing it
        Parameters
        ----------
        parmFile : str
           Name of file to parse
        """

        cf = SafeConfigParser()
        cf.read(parmFile)
        self._empty = 0
        self._model = []
        self._state = []
        status = int(cf.get('status', 'first'))
        if (status == 1):
            self._empty = 1
            return
        for m in cf.get('model', 'model_run').split():
            self._model.append(Model(m))
        
        for m in cf.get('forecast', 'forecast1').split():
            self._fState.append(ForecastStatus(m))

    def initialSetup(self, parms):
        """ Set state to have content, but empty details

        Will create one model (empty) and empty ForecastStatus for all leadtimes
        Parameters
        ----------
        parms : Parms
           Parameters

        """
        self._empty = 1
        self._model=[]
        self._fState = []
        self._model.append(Model())
        for i in range(0,parms._maxFcstHour):
            self._fState.append(ForecastStatus())

    def isEmpty(self):
        """ Check if empty
        Returns : bool
           true if empty
        """
        return (self._empty == 1)
    
    def debugPrint(self):
        """ WhfLog debug of content
        """
        for m in self._model:
            m.debugPrint()
        for f in self._fState:
            f.debugPrint()

    def initialize(self, parms, newest):
        """  Initialize state using inputs. Called when issue time changes.

        Parameters
        ----------
        parms : Parms
           Parameteres
        newest : str
           yyyymmddhh string for the new issue time
        """

        # convert to datetime
        itime = datetime.datetime.strptime(newest, '%Y%m%d%H')

        # if empty, prepare to add things, otherwise purge and add
        if (self._empty):
            self._empty = 0
            self._model = []
            self._fState = []

        # remove all stuff that is too old
        m2 = []
        for m in self._model:
            if (m.notTooOld(itime, parms._hoursBack)):
                m2.append(m)
        self._model = m2
        f2 = []
        for f in self._fState:
            if (f.notTooOld(itime, parms._hoursBack)):
                f2.append(f)
        self._fState = f2

        # the issue time is new, add a new model entry
        m = Model()
        m.setContent(itime)
        self._model.append(m)

        # the issue time is new, add new forecast entries for all lead times
        for i in range(0,parms._maxFcstHour):
            f = ForecastStatus()
            f.setContent(itime, i)
            self._fState.append(f)
        
    def write(self, parmFile):
        """ Write contents to a state file

        Parameters
        ----------
        parmFile : str
           Name of file to write to 
        """

        config = SafeConfigParser()

        config.add_section('status')
        if (self._empty == 1):
            config.set('status', 'first', '1')
        else:
            config.set('status', 'first', '0')


        # When adding sections or items, add them in the reverse order of
        # how you want them to be displayed in the actual file.
        # In addition, please note that using RawConfigParser's and the raw
        # mode of ConfigParser's respective set functions, you can assign
        # non-string values to keys internally, but will receive an error
        # when attempting to write to a file or when you get it in non-raw
        # mode. SafeConfigParser does not allow such assignments to take place.

        config.add_section('forecast')
        s = ""
        for f in self._fState:
            s += f.writeConfigString()
            s += "\n"

        config.set('forecast', 'forecast1', s)

        config.add_section('model')
        s = ""
        for f in self._model:
            s += f.writeConfigString()
            s += "\n"

        config.set('model', 'model_run', s)

        # Write it out
        with open(parmFile, 'wb') as configfile:
            config.write(configfile)

    def isNewModelIssueTime(self, issueTime):
        """ Check if input is a new model issue time or not

        Parameters
        ----------
        issueTime: str
            yyyymmddhh string
        Returns
        -------
        bool
            true if the input issue time is not in the state
        
        """
        itime = datetime.datetime.strptime(issueTime, '%Y%m%d%H')
        for m in self._model:
            if (m.inputIssueTimeEqual(itime)):
                return 0
        return 1
        
    
    def setCurrentModelAvailability(self, parms):
        """ Change availability status when appropriate by looking at disk
        Parameters
        ----------
        parms : Parms
           Params
        """
        for f in self._fState:

            # find matching model
            didSet = 0
            for m in self._model:
                 if (f.matches(m)):
                     didSet = 1
                     # need to pass that model in to check for 'very late'
                     f.setCurrentModelAvailability(parms, m)
            if (didSet == 0):
                WhfLog.error("No matching model for forecast")
                
    def layerIfReady(self, parms, configFile):
        """ Perform layering for all forecasts that indicate it should be done

        Parameters
        ----------
        parms : Parms
           Params
        configFile : string
           name of file with settings
        """
        for f in self._fState:
            f.layerIfReady(parms, configFile)
            
        
#----------------------------------------------------------------------------
def main(argv):

    # User must pass the config file into the main driver.
    configFile = argv[0]
    if not os.path.exists(configFile):
        print 'ERROR forcing engine config file not found.'
        return 1
    # read in fixed main params
    parms = parmRead(configFile)

    # query each directory to get newest thing, and update overall newest
    #WhfLog.debug("Looking in %s and %s", parms._hrrrDir, parms._rapDir)
    newestT = df.newestIssueTime(parms._hrrrDir)
    newestT2 = df.newestIssueTime(parms._rapDir)
    if (not newestT) and (not newestT2):
        WhfLog.debug("NO INPUT DATA available")
        return 0
    
    if (newestT2 > newestT):
        newestT = newestT2
    #WhfLog.debug("Newest issue time = %s", newestT)

    # if there is not a state file, create one now using newest
    if (not os.path.exists(parms._stateFile)):
        state = State()
        WhfLog.info("Initializing")
        state.initialSetup(parms)
        state.initialize(parms, newestT)
        state.write(parms._stateFile)

    # Normal processing situation
    #WhfLog.debug("Look for Layering....")
    
    # read in state
    state2 = State()
    state2.initFromStateFile(parms._stateFile)
    
    # check for new issue time
    if (state2.isNewModelIssueTime(newestT)):
        WhfLog.info("Re-Initializing state, new model issue time %s", newestT)
        state2.initialize(parms, newestT)

    # update availability
    state2.setCurrentModelAvailability(parms)

    # layer if appropriate
    state2.layerIfReady(parms, configFile)

    # write out final state
    state2.write(parms._stateFile)
    return 0

#----------------------------------------------

if __name__ == "__main__":
    main(sys.argv[1:])
