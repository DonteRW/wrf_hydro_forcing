import WRF_Hydro_forcing as whf
import Analysis_Assimilation_Forcing as aaf
import datetime
import re
from ConfigParser import SafeConfigParser


def is_within_time_range(start_dt, end_dt, file, prod, is_yellowstone=False):
    """Determines whether the file (full file path) is
       within the specified start and end time.
     
       Returns True if this file is within the specified
       start and end time, False otherwise.

    """
  
    # Get the date-time (YYYYMMDD) portion from
    # the filename, create a datetime object and
    # see if it lies within the start_dt and
    # end_dt datetimes.
    if is_yellowstone:
        if prod == 'MRMS':
            match = re.match(r'.*GaugeCorr.*00.00_([0-9]{8})_[0-9]{6}.*',file)
            ymd_dir = match.group(1)

        else:
            match = re.match(r'.*/(RAP|HRRR)/([0-9]{8})/[0-9]{8}_i[0-9]{2,3}_f[0-9]{2,3}_(WRF-RR|HRRR).*',file)
            ymd_dir = match.group(2)
    else: 
        if prod == 'MRMS':
            match = re.match(r'.*GaugeCorr.*00.00_([0-9]{8})_[0-9]{6}.*',file)
            ymd_dir = match.group(1)
        else:
            match = re.match(r'.*/([0-9]{8})/[0-9]{8}_i[0-9]{2}_f[0-9]{2,3}_(WRF-RR|HRRR).*',file)
            ymd_dir = match.group(1)

    # Create the datetime object for this ymd and compare
    ymd_datetime = datetime.datetime.strptime(ymd_dir, "%Y%m%d")
    if ymd_datetime >= start_dt and ymd_datetime <= end_dt:
        return True
    else:
        return False
    
def do_regrid(dir_base, prod, data_files, is_yellowstone):
    """Do the regridding and downscaling of the product"""
    
    for file in data_files:
        # Use only the filename of the file, the 
        # regrid_data() is only expecting a file name.
        if prod == 'MRMS':
            match = re.match(r'.*(GaugeCorr.*00.00_[0-9]{8}_[0-9]{6}.*)',file)
            file_only = match.group(1) 
        else:
            match = re.match(r'(.*)/([0-9]{8}_i[0-9]{2}_f[0-9]{2,3}.*)',file)
            file_only = match.group(2) 
        aaf.forcing("regrid",prod,file_only)


def do_layering(rap_downscale_dir, hrrr_downscale_dir, mrms_downscale_dir, is_yellowstone=False):
    # Go through the RAP downscaled directories and find 
    # the corresponding HRRR downscaled file for each RAP
    # file.
    rap_file_paths = whf.get_filepaths(rap_downscale_dir)
    if hrrr_downscale_dir is NONE:
        no_hrrr = True
    else:
        hrrr_file_paths = whf.get_filepaths(hrrr_downscale_dir)
    if mrms_downscale_dir is NONE:
        no_mrmrs = True
    else:
        mrms_file_paths = whf.get_filepaths(mrms_downscale_dir)
    
    # Compare the YYYYMMDDHH/YYYYMMDDhh00.LDASIN_DOMAIN1.nc portions
    rap_files = []
    hrrr_files = []
    mrms_files = []
    if is_yellowstone:    
        for rap in rap_file_paths:
             match = re.match(r'.*/RAP/[0-9]{8}/([0-9]{8}_i[0-9]{2}_f[0-9]{2,3}.*)',rap)
             rap_files.append(match.group(1)) 
        
        for hrrr in hrrr_file_paths:
             match = re.match(r'.*/HRRR/[0-9]{8}/([0-9]{8}_i[0-9]{2}_f[0-9]{2,3}.*)',hrrr)
             hrrr_files.append(match.group(1)) 
    else:
        for rap in rap_file_paths:
            match = re.match(r'.*/[0-9]{8}/([0-9]{8}_i[0-9]{2}_f[0-9]{2,3}.*)',rap)
            rap_files.append(match.group(1))
        for hrrr in hrrr_file_paths:
            match = re.match(r'.*/[0-9]{8}/([0-9]{8}_i[0-9]{2}_f[0-9]{2,3}.*)',hrrr)
            hrrr_files.append(match.group(1))

    # Find the matching files from each list
    files_to_layer = set(rap_files) & set(hrrr_files)
    for file in files_to_layer:
        aaf.forcing("layer","RAP", file, "HRRR", file)
        



def main():
    """Tests the regridding and downscaling of RAP and HRRR
       data for the Short Range Forcing Configuration.
    """
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # CHANGE THIS TO REFLECT WHICH RUN ENVIRONMENT:
    # YELLOWSTONE OR HYDRO-C!
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # Set flag for testing host
    is_yellowstone = True
    #is_yellowstone = False
    parser = SafeConfigParser()
    parser.read('wrf_hydro_forcing.parm')    

    # Start and end dates 
    if is_yellowstone:
         start_dt = datetime.datetime.strptime("20150930","%Y%m%d")
         end_dt = datetime.datetime.strptime("20150930","%Y%m%d")
    else:
         start_dt = datetime.datetime.strptime("20151126","%Y%m%d")
         end_dt = datetime.datetime.strptime("20151126","%Y%m%d")

    # Set the directory where the input data resides.
    # For running on yellowstone:
    # RAP_dir_base = "/glade/scratch/lpan/IOC/data/RAP"
    # HRRR_dir_base = "/glade/scratch/lpan/IOC/data/HRRR"
    # MRMS_dir_base = "/glade/scratch/lpan/IOC/data/MRMS"
    # For running on hydro-c1:
    # RAP_downscale_dir =
    # "/glade/scratch/gochis/IOC_evaluation_datasets/
    # Forcing_Engine/workspace/downscaled/RAP"
    # HRRR_downscale_dir = "/glade/scratch/gochis/
    # IOC_evaluation_datasets/Forcing_Engine/workspace/downscaled/HRRR"
    #RAP_dir_base = parser.get('data_dir','RAP_data')
    HRRR_dir_base = parser.get('data_dir', 'HRRR_data')
   # MRMS_dir_base = parser.get('data_dir', 'MRMS_data')
    #RAP_downscale_dir = parser.get('downscaling', 'RAP_downscale_output_dir')
    HRRR_downscale_dir = parser.get('downscaling', 'HRRR_downscale_output_dir')

    #all_RAP_files_with_path = whf.get_filepaths(RAP_dir_base) 
    all_HRRR_files_with_path = whf.get_filepaths(HRRR_dir_base) 
    #all_MRMS_files_with_path = whf.get_filepaths(MRMS_dir_base) 

    # We are only interested in the MRMS, RAP and HRRR files that are
    # within the start and end forecast times, since the /glade/scratch/lpan/IOC/data
    # directory is continually adding more dates.
    #RAP_files_with_path = [x for x in all_RAP_files_with_path if is_within_time_range(start_dt,end_dt,x,"RAP",is_yellowstone)]
    HRRR_files_with_path = [x for x in all_HRRR_files_with_path if is_within_time_range(start_dt,end_dt,x,"HRRR",is_yellowstone)]
        
    #MRMS_files_with_path = [x for x in all_MRMS_files_with_path if is_within_time_range(start_dt,end_dt,x,"MRMS",is_yellowstone)]

    for hrrr in HRRR_files_with_path:
        print ("process %s")%(hrrr)
    # do the processing on only the input grib files 
   # do_regrid(RAP_dir_base,'RAP', RAP_files_with_path, is_yellowstone)
    do_regrid(HRRR_dir_base, 'HRRR', HRRR_files_with_path, is_yellowstone)
    #do_regrid(MRMS_dir_base, 'MRMS', MRMS_files_with_path, is_yellowstone)
    #do_layering(RAP_downscale_dir, HRRR_downscale_dir, is_yellowstone)




#----------------------------------------------------------------------------------------         
    
if __name__ == "__main__":
    main()    

