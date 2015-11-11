import os
import errno
import logging
import re
import time
import numpy as np
import argparse
import datetime
import sys
from ConfigParser import SafeConfigParser



# -----------------------------------------------------
#             WRF_Hydro_forcing.py
# -----------------------------------------------------

#  Overview:
#  This is a forcing engine for WRF Hydro. It serves as a wrapper
#  to the regridding and other processing scripts written in NCL.  
#  This script was created to conform with NCEP Central Operations
#  WCOSS implementation standards and as part of the workflow for
#  operating at the National Water Center (NWC).  Input variables 
#  to the NCL scripts are defined in a parm/config file: 
#  wrf_hydro_forcing.parm to reduce the requirement to set environment
#  variables for input file directories, output file directories,
#  etc. which are not always conducive in an operational setting.



def regrid_data( product_name, file_to_regrid, parser, substitute_fcst = False ):
    """Provides a wrapper to the regridding scripts originally
    written in NCL.  For HRRR data regridding, the
    HRRR-2-WRF_Hydro_ESMF_forcing.ncl script is invoked.
    For MRMS data MRMS-2-WRF_Hydro_ESMF_forcing.ncl is invoked.
    Finally, for NAM212 data, NAM-2-WRF_Hydro_ESMF_forcing.ncl 
    is invoked.  All product files (HRRR, MRMS, NAM, RAP etc.) are
    retrieved and stored in a list. The appropriate regridding
    script is invoked for each file in the list.  The regridded
    files are stored in an output directory defined in the
    parm/config file.

    Args:
        product_name (string):  The name of the product 
                                e.g. HRRR, MRMS, NAM
        file_to_regrid (string): The filename of the
                                  input data to process.
        parser (ConfigParser):  The parser to the config/parm
                                file containing all defined values
                                necessary for running the regridding.
        substitute_fcst (bool):  Default = False If this is a 0 hr
                               forecast file, then skip regridding,
                               it will need to be replaced with
                               another file during the 
                               downscale_data() step.
    Returns:
        regridded_output (string): The full filepath and filename
                                   of the regridded file.  If thd data
                                   product is GFS or RAP and it is the
                                   f000 file, then just create an
                                   empty file that follows the naming
                                   convention of a regridded file.

    """


    # Retrieve the values from the parm/config file
    # which are needed to invoke the regridding 
    # scripts.
    product = product_name.upper()
    ncl_exec = parser.get('exe', 'ncl_exe')


    if product == 'HRRR':
       logging.info("Regridding HRRR")
       wgt_file = parser.get('regridding', 'HRRR_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'HRRR_data')
       regridding_exec = parser.get('exe', 'HRRR_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','HRRR_output_dir')
       dst_grid_name = parser.get('regridding','HRRR_dst_grid_name')
    elif product == 'MRMS':
       logging.info("Regridding MRMS")
       wgt_file = parser.get('regridding', 'MRMS_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'MRMS_data')
       regridding_exec = parser.get('exe', 'MRMS_regridding_exe')
       #data_files_to_process = get_filepaths(data_dir)   
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','MRMS_output_dir')
       dst_grid_name = parser.get('regridding','MRMS_dst_grid_name')
    elif product == 'NAM':
       logging.info("Regridding NAM")
       wgt_file = parser.get('regridding', 'NAM_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'NAM_data')
       regridding_exec = parser.get('exe', 'NAM_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','NAM_output_dir')
       dst_grid_name = parser.get('regridding','NAM_dst_grid_name')
    elif product == 'GFS':
       logging.info("Regridding GFS")
       wgt_file = parser.get('regridding', 'GFS_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'GFS_data')
       regridding_exec = parser.get('exe', 'GFS_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','GFS_output_dir')
       dst_grid_name = parser.get('regridding','GFS_dst_grid_name')
    elif product == 'RAP':
       logging.info("Regridding RAP")
       wgt_file = parser.get('regridding', 'RAP_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'RAP_data')
       regridding_exec = parser.get('exe', 'RAP_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','RAP_output_dir')
       dst_grid_name = parser.get('regridding','RAP_dst_grid_name')


    # If this is a 0hr forecast and the data product is either GFS or RAP, then do
    # nothing for now, it will need to be replaced during the
    # downscaling step.
    if substitute_fcst:
        logging.info("Inside regrid_data(). Skip regridding f0 RAP...")
        (subdir_file_path,hydro_filename) = \
            create_output_name_and_subdir(product,file_to_regrid,data_dir)
        regridded_file_path = output_dir_root + "/" + subdir_file_path 
        regridded_file = output_dir_root + "/" + subdir_file_path + "/" + hydro_filename 
        mkdir_p(regridded_file_path)
        touch_cmd = "touch " + regridded_file
        os.system(touch_cmd)
        return regridded_file  
        
    else:

        # Generate the key-value pairs for 
        # input to the regridding script.
        # The key-value pairs for the input should look like: 
        #  'srcfilename="/d4/hydro-dm/IOC/data/HRRR/20150723_i23_f010_HRRR.grb2"' 
        #  'wgtFileName_in=
        #     "d4/hydro-dm/IOC/weighting/HRRR1km/HRRR2HYDRO_d01_weight_bilinear.nc"'
        #  'dstGridName="/d4/hydro-dm/IOC/data/geo_dst.nc"' 
        #  'outdir="/d4/hydro-dm/IOC/regridded/HRRR/20150723/i09"'
        #  'outFile="201507241900.LDASIN_DOMAIN1.nc"' 
       
        (date,model,fcsthr) = extract_file_info(file_to_regrid)  
        data_file_to_regrid= data_dir + "/" + date + "/" + file_to_regrid 
        srcfilename_param =  "'srcfilename=" + '"' + data_file_to_regrid +  \
                                 '"' + "' "
        # logging.info("input data file: %s", file_to_regrid)
        wgtFileName_in_param =  "'wgtFileName_in = " + '"' + wgt_file + \
                                    '"' + "' "
        dstGridName_param =  "'dstGridName=" + '"' + dst_grid_name + '"' + "' "
    
        # Create the output filename following the RAL 
        # naming convention: 
        (subdir_file_path,hydro_filename) = \
            create_output_name_and_subdir(product,data_file_to_regrid,data_dir)
       
        #logging.info("hydro filename: %s", hydro_filename)
        # Create the full path to the output directory
        # and assign it to the output directory parameter
        output_file_dir = output_dir_root + "/" + subdir_file_path
        outdir_param = "'outdir=" + '"' + output_file_dir + '"' + "' " 
        regridded_file = output_file_dir + hydro_filename

        if product == "HRRR" or product == "NAM" \
           or product == "GFS" or product == "RAP":
           full_output_file = output_file_dir + "/"  
           # Create the new output file subdirectory
           mkdir_p(output_file_dir)
           outFile_param = "'outFile=" + '"' + hydro_filename+ '"' + "' "
        elif product == "MRMS":
           # !!!!!!NOTE!!!!!
           # MRMS regridding script differs from the HRRR and NAM scripts in that 
           # it does not # accept an outdir variable.  Incorporate the output
           # directory (outdir) into the outFile variable.
           full_output_file = output_file_dir + "/"  + hydro_filename
           mkdir_p(output_file_dir)
           outFile_param = "'outFile=" + '"' + full_output_file + '"' + "' "

        regrid_params = srcfilename_param + wgtFileName_in_param + \
                    dstGridName_param + outdir_param + \
                    outFile_param
        regrid_prod_cmd = ncl_exec + " "  + regrid_params + " " + \
                      regridding_exec
    
        logging.debug("regridding command: %s",regrid_prod_cmd)

        # Measure how long it takes to run the NCL script for regridding.
        start_NCL_regridding = time.time()
        return_value = os.system(regrid_prod_cmd)
        end_NCL_regridding = time.time()
        elapsed_time_sec = end_NCL_regridding - start_NCL_regridding
        logging.info("Time(sec) to regrid file  %s" %  elapsed_time_sec)
 

        if return_value != 0:
            logging.info('ERROR: The regridding of %s was unsuccessful, \
                          return value of %s', product,return_value)
            #TO DO: Determine the proper action to take when the NCL file h
            #fails. For now, exit.
            sys.exit()
    

    return regridded_file

def get_filepaths(dir):
    """ Generates the file names in a directory tree
    by walking the tree either top-down or bottom-up.
    For each directory in the tree rooted at 
    the directory top (including top itself), it
    produces a 3-tuple: (dirpath, dirnames, filenames).
    
    Args:
        dir (string): The base directory from which we 
                      begin the search for filenames.
    Returns:
        file_paths (list): A list of the full filepaths 
                           of the data to be processed.

        
    """

    # Create an empty list which will eventually store 
    # all the full filenames
    file_paths = []

    # Walk the tree
    for root, directories, files in os.walk(dir):
        for filename in files:
            # Join the two strings to form the full
            # filepath.
            filepath = os.path.join(root,filename)
            # add it to the list
            file_paths.append(filepath)
    return file_paths



    
def create_output_name_and_subdir(product, filename, input_data_file):
    """ Creates the full filename for the regridded data which ties-in
       to the WRF-Hydro Model expected input: 
       (RAL) basedir/YYYYMMDD/i_hh/YYMMDD_ihh_fnnnn_<product>.nc
       (WRF-Hydro Model) basedir/<product>/YYYYMMDDHH/YYMMDDhh00_LDASIN_DOMAIN1.nc
    Where the HH is the model run time/init time in hours
    hh00 is the valid time in hours and 00 minutes and <product> is the
    name of the model/data product:  e.g. HRRR, NAM, MRMS, GFS, etc.
    The valid time is the sum of the model run time (aka init time) and the
    forecast time (fnnnn) in hours.  If the valid time exceeds 24 hours, the
    YYYYMMDD is incremented appropriately to reflect how many days into the
    future the valid time represents.

    Args:
        product (string):  The product name: HRRR, MRMS, or NAM.

        filename (string): The name of the input data file:
                           YYYYMMDD_ihh_fnnn_product.grb

        input_data_file (string):  The full path and name
                                  of the (input) data 
                                  files:
                                  /d4/hydro-dm/IOC/data/product/...
                                  This is used to create the output
                                  data dir and filename from the
                                  datetime, init, and forecast
                                  portions of the filename.

        output_dir_root (string): The root directory for output:
                                  /d4/hydro-dm/IOC/regridded/<product>
                                  Used to create the full path.

    Returns:
        
        year_month_day_subdir (string): The subdirectory under which the 
                                        processed files will be stored:
                                        YYYYMMDDHH/
                                        HH= model run hour

        hydro_filename (string):  The name of the processed output
                                  file:YYYYMMDDhh00.LDASIN_DOMAIN1      
                                  where hh is the valid time adjusted
                                  for 24-hour time.  Valid time is the
                                  sum of the fcst hour and the model 
                                  run (init time).
 
    """

    # Convert product to uppercase for easy, consistent 
    # comparison.
    product_name = product.upper() 

    if product == 'HRRR' or product == 'GFS' \
       or product == "NAM" or product == 'RAP':
        match = re.match(r'.*([0-9]{8})_(i[0-9]{2})_(f[0-9]{2,4})',filename)
        if match:
            year_month_day = match.group(1)
            init_hr = match.group(2)
            fcst_hr = match.group(3)
            year_month_day_subdir = year_month_day + init_hr 
        else:
            logging.error("ERROR [create_output_name_and_subdir]: %s data filename %s has an unexpected name.", \
                           product_name,filename) 
            sys.exit()

    elif product == 'MRMS':
        match = re.match(r'.*([0-9]{8})_([0-9]{2}).*',filename) 
        if match:
           year_month_day = match.group(1)
           init_hr =  match.group(2)

           # Radar data- not a model, therefore no forecast
           # and valid time is the init time
           valid_time = init_hr
           year_month_day_subdir = year_month_day + init_hr 
        else:
           logging.error("ERROR: MRMS data filename %s \
                          has an unexpected file name.",\
                          filename) 
           sys.exit()

   
    if valid_time >= 24:
        num_days_ahead =  valid_time / 24
        # valid time in 24 hour time
        valid_time_str =  str(valid_time % 24)
        valid_time_corr = valid_time_str.rjust(2,'0')
        updated_date = get_past_or_future_date(year_month_day, num_days_ahead)
        # Assemble the filename and the full output directory path
        hydro_filename = year_month_day + init_hr + "/" + updated_date + valid_time_corr +\
                         "00.LDASIN_DOMAIN1" 
    else:
        # Assemble the filename and the full output directory path
        hydro_filename = year_month_day +  init_hr + "/" + \
                         year_month_day + valid_time + "00.LDASIN_DOMAIN1" 
        #logging.debug("Generated the output filename for %s: %s",product, hydro_filename)

    return (year_month_day_subdir, hydro_filename)




def mkdir_p(dir):
    """Provides mkdir -p functionality.
    
       Args:
          dir (string):  Full directory path to be created if it
                         doesn't exist.
       Returns:
          None:  Creates nested subdirs if they don't already 
                 exist.

    """
    try:
       os.makedirs(dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(dir):
            pass
        else: raise            


def downscale_data(product_name, file_to_downscale, parser, downscale_shortwave=False,
                   substitute_fcst=False):
    """
    Performs downscaling of data by calling the necessary
    NCL code (specific to the model/product).  There is an
    additional option to downscale the short wave radiation, SWDOWN.  
    If downscaling SWDOWN (shortwave radiation) is requested  
    then a second NCL script is invoked (topo_adj.ncl).  This second 
    NCL script invokes a Fortran application (topo_adjf90.so, 
    built from topo_adj.f90). 

    NOTE:  If the additional downscaling
    (of shortwave radiation) is requested, the adj_topo.ncl script
    will "clobber" the previously created downscaled files.


    Args:
        product_name (string):  The product name: ie HRRR, NAM, GFS, etc. 
      
        file_to_downscale (string): The file to be downscaled, this is 
                                 the full file path to the regridded
                                 file.

        parser (ConfigParser) : The ConfigParser which can access the
                                Python config file wrf_hydro_forcing.parm
                                and retrieve the file names and locations
                                of input.

        downscale_shortwave (boolean) : 'True' if downscaling of 
                                shortwave radiation (SWDOWN) is 
                                requested; invoke topo_adj.ncl, 
                                the NCL wrapper to the Fortan
                                code.
                                Set to 'False' by default.

        substitute_fcst (boolean) : 'True'- if this is a zero hour 
                                  forecast, then copy the downscaled 
                                  file from a previous model run with 
                                  the same valid time and rename it.
                                  'False' by default.
                                  
    Returns:
        None

        
    """

    # Read in all the relevant input parameters based on the product: 
    # HRRR, NAM, GFS, etc.
    product = product_name.upper() 
    lapse_rate_file = parser.get('downscaling','lapse_rate_file')
    ncl_exec = parser.get('exe', 'ncl_exe')
    

    if product  == 'HRRR':
        logging.info("Downscaling HRRR")
        data_to_downscale_dir = parser.get('downscaling','HRRR_data_to_downscale')
        hgt_data_file = parser.get('downscaling','HRRR_hgt_data')
        geo_data_file = parser.get('downscaling','HRRR_geo_data')
        downscale_output_dir = parser.get('downscaling', 'HRRR_downscale_output_dir')
        downscale_exe = parser.get('exe', 'HRRR_downscaling_exe')
    elif product == 'NAM':
        logging.info("Downscaling NAM")
        data_to_downscale_dir = parser.get('downscaling','NAM_data_to_downscale')
        hgt_data_file = parser.get('downscaling','NAM_hgt_data')
        geo_data_file = parser.get('downscaling','NAM_geo_data')
        downscale_output_dir = parser.get('downscaling', 'NAM_downscale_output_dir')
        downscale_exe = parser.get('exe', 'NAM_downscaling_exe')
    elif product == 'GFS':
        logging.info("Downscaling GFS")
        data_to_downscale_dir = parser.get('downscaling','GFS_data_to_downscale')
        hgt_data_file = parser.get('downscaling','GFS_hgt_data')
        geo_data_file = parser.get('downscaling','GFS_geo_data')
        downscale_output_dir = parser.get('downscaling', 'GFS_downscale_output_dir')
        logging.info("GFS data to downscale: %s ", downscale_output_dir)
        downscale_exe = parser.get('exe', 'GFS_downscaling_exe')
    elif product == 'RAP':
        logging.info("Downscaling RAP")
        data_to_downscale_dir = parser.get('downscaling','RAP_data_to_downscale')
        hgt_data_file = parser.get('downscaling','RAP_hgt_data')
        geo_data_file = parser.get('downscaling','RAP_geo_data')
        downscale_output_dir = parser.get('downscaling', 'RAP_downscale_output_dir')
        downscale_exe = parser.get('exe', 'RAP_downscaling_exe')
    else:
        logging.info("Requested downscaling of unsupported data product %s", product)
 
     
    # If this is an f000 file and is either RAP or GFS, then search for
    # a suitable replacement since this file will have one or more 
    # missing variable(s).
    # Otherwise, proceed with creating the request to downscale.
 
    if substitute_fcst:
        # Don't downscale, find another downscaled file from the previous model
        # run with the same valid time (model run + fcst hour = valid time) and
        # copy to this f000 file.
        logging.info("Searching for f000 substitute...")
        replace_fcst0hr(parser, file_to_downscale,product)

    else:
        # Downscale as usual

        #match = re.match(r'(.*)/(([0-9]{8})_(i[0-9]{2})_f.*)',file_to_downscale)
        match = re.match(r'(.*)/(([0-9]{8})([0-9]{2})00.LDASIN_DOMAIN1)',file_to_downscale)
        if match:
            yr_month_day = match.group(3)
            downscaled_file = match.group(2)
            valid_hr = match.group(4)
        else:
            logging.error("ERROR: regridded file's name: %s is an unexpected format",\
                               data)
            sys.exit() 
   
        full_downscaled_dir = downscale_output_dir + "/" + yr_month_day + "/"\
                                + valid_hr  
        full_downscaled_file = full_downscaled_dir + "/" +  downscaled_file
        # Create the full output directory for the downscaled data if it doesn't 
        # already exist. 
        mkdir_p(full_downscaled_dir) 
    
        logging.info("full_downscaled_file: %s", full_downscaled_file)
        logging.debug("Full output filename for second downscaling: %s" , full_downscaled_file)
    
        # Create the key-value pairs that make up the
        # input for the NCL script responsible for
        # the downscaling.
        input_file1_param = "'inputFile1=" + '"' + hgt_data_file + '"' + "' "
        input_file2_param = "'inputFile2=" + '"' + geo_data_file + '"' + "' "
        input_file3_param = "'inputFile3=" + '"' + data + '"' + "' "
        lapse_file_param =  "'lapseFile=" + '"' + lapse_rate_file + '"' + "' "
        output_file_param = "'outFile=" + '"' + full_downscaled_file + '"' + "' "
        downscale_params =  input_file1_param + input_file2_param + \
                  input_file3_param + lapse_file_param +  output_file_param 
        downscale_cmd = ncl_exec + " " + downscale_params + " " + downscale_exe
        logging.debug("Downscale command : %s", downscale_cmd)
    
        # Downscale the shortwave radiation, if requested...
        # Key-value pairs for downscaling SWDOWN, shortwave radiation.
        if downscale_shortwave:
            logging.info("Shortwave downscaling requested...")
            downscale_swdown_exe = parser.get('exe', 'shortwave_downscaling_exe') 
            swdown_output_file_param = "'outFile=" + '"' + \
                                       full_downscaled_file + '"' + "' "
    
            swdown_geo_file_param = "'inputGeo=" + '"' + geo_data_file + '"' + "' "
            swdown_params = swdown_geo_file_param + " " + swdown_output_file_param
            downscale_shortwave_cmd = ncl_exec + " " + swdown_params + " " \
                                      + downscale_swdown_exe 
            logging.info("SWDOWN downscale command: %s", downscale_shortwave_cmd)
    
            # Crude measurement of performance for downscaling.
            # Wall clock time used to determine the elapsed time
            # for downscaling each file.
            start = time.time()
    
            #Invoke the NCL script for performing a single downscaling.
            return_value = os.system(downscale_cmd)
            swdown_return_value = os.system(downscale_shortwave_cmd)
            end = time.time()
            elapsed = end - start
    
            # Check for successful or unsuccessful downscaling
            # of the required and shortwave radiation
            if return_value != 0 or swdown_return_value != 0:
                logging.info('ERROR: The downscaling of %s was unsuccessful, \
                             return value of %s', product,return_value)
                sys.exit()
    
        else:
            # No additional downscaling of
            # the short wave radiation is required.
    
            # Crude measurement of performance for downscaling.
            start = time.time()
    
            #Invoke the NCL script for performing the generic downscaling.
            return_value = os.system(downscale_cmd)
            end = time.time()
            elapsed = end - start
            logging.info("Elapsed time (sec) for downscaling: %s",elapsed)
    
            # Check for successful or unsuccessful downscaling
            if return_value != 0:
                logging.info('ERROR: The downscaling of %s was unsuccessful, \
                             return value of %s', product,return_value)
                #TO DO: Determine the proper action to take when the NCL file 
                #fails. For now, exit.
                sys.exit()
    
    






# STUB for BIAS CORRECTION, TO BE
# IMPLEMENTED LATER...
def bias_correction(parser):
    """ STUB TO BE IMPLEMENTED
    """
#
#



def layer_data(parser, primary_data, secondary_data):
    """ Invokes the NCL script, combine.ncl
        to layer/combine two files:  a primary and secondary
        file (with identical date/time, model run time, and
        forecast time) are found by iterating through a list
        of primary files and determining if the corresponding
        secondary file exists.


        Args:
              parser (ConfigParser):  The parser to the config/parm
                                      file containing all the defined
                                      values.
              primary_data (string):  The name of the primary product
 
              secondary_data (string): The name of the secondary product

        Output:
              None:  For each primary and secondary file that is
                     combined/layered, create a file
                     (name and location defined in the config/parm 
                     file).
    """

    # Retrieve any necessary parameters from the wrf_hydro_forcing config/parm
    # file...
    # 1) directory where HRRR and RAP downscaled data reside
    # 2) output directory where layered files will be saved
    # 3) location of any executables/scripts
    ncl_exe = parser.get('exe', 'ncl_exe')
    layering_exe = parser.get('exe','Analysis_Assimilation_layering')
    downscaled_primary_dir = parser.get('layering','analysis_assimilation_primary')
    downscaled_secondary_dir = parser.get('layering','analysis_assimilation_secondary')
    layered_output_dir = parser.get('layering','output_dir')


    # Loop through any available files in
    # the directory that defines the first choice/priority data.
    # Assemble the name of the corresponding secondary filename
    # by deriving the date and model run (YYYYMMDDHH)
    # from the primary filename and path.
    # Then check if this file exists, if so, then pass this pair into
    # a list of tuples comprised of (primary file, secondary file).
    # After a list of paired files has been completed, these files
    # will be layered/combined by invoking the NCL script, combine.ncl.
    primary_files = get_filepaths(downscaled_primary_dir)
    
    # Determine which primary and secondary files we can layer, based on
    # matching dates, model runs, and forecast times.
    list_paired_files = find_layering_files(primary_files, downscaled_secondary_dir)
    
    # Now we have all the paired files to layer, create the key-value pair of
    # input needed to run the NCL layering script.
    num_matched_pairs = len(list_paired_files)
    for pair in list_paired_files:
        hrrrFile_param = "'hrrrFile=" + '"' + pair[0] + '"' + "' "
        rapFile_param =  "'rapFile="  + '"' + pair[1] + '"' + "' "
        full_layered_outfile = layered_output_dir + "/" + pair[2]
        outFile_param = "'outFile=" + '"' + full_layered_outfile + '"' + "' "
        mkdir_p(full_layered_outfile)
        init_indexFlag = "false"
        indexFlag = "true"
        init_indexFlag_param = "'indexFlag=" + '"' +  init_indexFlag + '"' + "' "
        indexFlag_param = "'indexFlag=" + '"' + indexFlag + '"' + "' "
        init_layering_params = hrrrFile_param + rapFile_param + init_indexFlag_param\
                               + outFile_param 
        layering_params = hrrrFile_param + rapFile_param + indexFlag_param\
                          + outFile_param
        init_layering_cmd = ncl_exe + " " + init_layering_params + " " + \
                            layering_exe
        layering_cmd = ncl_exe + " " + layering_params + " " + \
                            layering_exe
         
        init_return_value = os.system(init_layering_cmd)
        return_value = os.system(layering_cmd) 
    
    
def find_layering_files(primary_file,downscaled_secondary_dir):
    """Given a primary file (full path + filename),
    retrieve the corresponding secondary file if it exists.  
    Create and return a tuple: (primary file, secondary file, 
    layered file). 

    Args:
        primary_files(string):  The primary file for
                              which we are trying to find
                              it's layering complement in
                              the secondary file directory
        downscaled_secondary_dir(string): The directory 
                                          that contains the
                                          secondary data.
    Output:
        list_paired_files (tuple of strings): A list of tuples, where 
                                  the tuple consists of 
                                  (primary file, secondary
                                   file, and layered file name)
        
 
    """
    second_product = "RAP"
    list_paired_files = []
    paired_files = ()

    for primary_file in primary_files:
        #match = re.match(r'.*/downscaled/([A-Za-z]{3,4})/([0-9]{8})/i([0-9]{2})/[0-9]{8}_i[0-9]{2}_f([0-9]{3})_[A-Za-z]{3,4}.nc',primary_file)
        match = re.match(r'.*/downscaled/([A-Za-z]{3,4})/([0-9]{8})([0-9]{2})/[0-9]{8}([0-9]{2})00.LDASIN_DOMAIN1.*',primary_file)
        if match:
            product = match.group(1)
            date = match.group(2)
            modelrun_str = match.group(3)
            valid_hr_str = match.group(4)
            # Assemble the corresponding secondary file based on the date, modelrun, 
            # and forecast hour. 
            secondary_file = downscaled_secondary_dir +  \
                             "/" + date +  modelrun_str + "/" + date +\
                             valid_hr_str + "00.LDASIN_DOMAIN1" +\
                             second_product 
            layered_filename = date + valid_hr_str + "00.LDASIN_DOMAIN1" 
               
        
            # Determine if this "manufactured" secondary file exists, if so, then 
            # create a tuple to represent this pair: (primary file, 
            # secondary file, layered file) then add this tuple of 
            # files to the list and continue. If not, then continue 
            # with the next primary file in the primary_files list.
            if os.path.isfile(secondary_file):
                paired_files = (primary_file, secondary_file,layered_filename)
                list_paired_files.append(paired_files)
                num = len(list_paired_files)
            else:
                logging.info("No matching date, or model run or forecast time for\
                             #secondary file")
                continue
        else:
            logging.error('ERROR [find_layering_files]: filename structure is not what was expected')
            sys.exit()



    return list_paired_files


def read_input():
    """   Reads in the command line arguments.


          Args:
            None
  
          Returns:
            args (args structure from argparse):  The struct from argparse
 
    """
    parser = argparse.ArgumentParser(description='Forcing Configurations for WRF-Hydro')
    # Actions
    parser.add_argument('--regrid_downscale', action='store_true', help='regrid and downscale')
    parser.add_argument('--bias', action='store_true', help='bias correction')
    parser.add_argument('--layer', action='store_true', help='layer')

    # Product name of input data
    parser.add_argument('--DataProductName', required = True, choices=['MRMS','RAP','HRRR','GFS','CFS'],help='input data name: MRMS, RAP, HRRR, GFS, CFS')


    # Input file
    parser.add_argument('InputFileName')
    args = parser.parse_args()
    if not (args.regrid_downscale or args.layer or args.bias) :
        parser.error('No action was requested, request regridding/downscaling, bias-correction, or layering')

    return args



def initial_setup(parser,forcing_config_label):
    """  Set up any environment variables, logging levels, etc.
         before any processing begins.

         Args:
            parser (SafeConfigParser):  the parsing object 
                                          necessary for parsing
                                          the config/parm file.
            forcing_config_label (string):  The name of the log
                                          file to associate with
                                          the forcing configuration.
                            
         Returns:
            logging (logging):  The logging object to which we can
                                write.   
                                           
    """

    #Read in all relevant params from the config/param file
    ncl_exec = parser.get('exe', 'ncl_exe')
    ncarg_root = parser.get('default_env_vars', 'ncarg_root')
    logging_level = parser.get('log_level', 'forcing_engine_log_level')

    # Check for the NCARG_ROOT environment variable. If it is not set,
    # use an appropriate default, defined in the configuration file.
    ncarg_root_found = os.getenv("NCARG_ROOT")
    if ncarg_root_found is None:
        ncarg_root = os.environ["NCARG_ROOT"] = ncarg_root

    # Set the NCL_DEF_LIB_DIR to indicate where ALL shared objects
    # reside.
    ncl_def_lib_dir = parser.get('default_env_vars','ncl_def_lib_dir')
    ncl_def_lib_dir = os.environ["NCL_DEF_LIB_DIR"] = ncl_def_lib_dir

    # Set the logging level based on what was defined in the parm/config file
    if logging_level == 'DEBUG':
        set_level = logging.DEBUG
    elif logging_level == 'INFO':
        set_level = logging.INFO
    elif logging_level == 'WARNING':
        set_level = logging.WARNING
    elif logging_level == 'ERROR':
        set_level = logging.ERROR
    else:
        set_level = logging.CRITICAL

    logging_filename =  forcing_config_label + ".log"
    logging.basicConfig(format='%(asctime)s %(message)s',
                         filename=logging_filename, level=set_level)

    return logging     

def extract_file_info(input_file):

    """ Extract the date, model run time (UTC) and
        forecast hour (UTC) from the input file name.

        Args:
            input_file (string):  Contains the date, model run
                                  time (UTC) and the forecast
                                  time in UTC.
        Returns:
            date (string):  YYYYMMDD
            model_run (int): HH
            fcst_hr (int):  HHH
    """

    # Regexp check for model data
    match = re.match(r'.*([0-9]{8})_i([0-9]{2})_f([0-9]{3,4}).*.[grb|nc|]', input_file)

    # Regexp check for MRMS data
    match2 = re.match(r'.*(GaugeCorr_QPE_00.00)_([0-9]{8})_([0-9]{6})',input_file)
    if match:
       date = match.group(1)
       model_run = int(match.group(2))
       fcst_hr  = int(match.group(3))
       return (date, model_run, fcst_hr)
    elif match2:
       date = match2.group(2)
       model_run = match2.group(3)
       fcst_hr = 0
       return (date, model_run, fcst_hr)
    else:
        logging.error("ERROR [extract_file_info]: File name doesn't follow expected format")


def is_in_fcst_range(product_name,fcsthr, parser):
    """  Determine if this current file to be processed has a forecast
         hour that falls within the range bound by the max forecast hour 
         Supports checking for RAP, HRRR, and GFS data.  
         
         Args:
            fcsthr (int):  The current file's (i.e. the data file under
                           consideration) forecast hour.
            parser (SafeConfigParser): The parser object. 
     
         Returns:
            boolean:  True if this is within the max forecast hour
                      False otherwise.
                           
    """

    # Determine whether this current file lies within the forecast range
    # for this data (e.g. if processing RAP, use only the 0hr-18hr forecasts).
    # Skip if this file corresponds to a forecast hour outside of the range.
    if product_name == 'RAP':
        fcst_max = int(parser.get('fcsthr_max','RAP_fcsthr_max'))
    elif product_name == 'HRRR':
        fcst_max = int(parser.get('fcsthr_max','HRRR_fcsthr_max'))
    elif product_name == 'GFS':
        fcst_max = int(parser.get('fcsthr_max','GFS_fcsthr_max'))
    elif product_name == 'CFS':
        fcst_max = int(parser.get('fcsthr_max','CFS_fcsthr_max'))
    elif product_name == 'MRMS':
        # MRMS is from observational data, no forecasted data, just
        # return True...
        return True
        
      
    if fcsthr >= fcst_max:
        logging.info("Skip file, fcst hour %d is outside of fcst max %d",fcsthr,fcst_max)
        return False
    else:
        return True






def replace_fcst0hr(parser, file_to_replace, product):
    """   For the 0hr forecasts of GFS or RAP data,
          substitute with the downscaled data from the previous
          model run with the same valid time, where valid time
          is the model run time (UTC) + forecast hour (UTC).
          This is necessary, as there are some missing variables
          in the 0hr forecast for RAP and GFS, which cause
          problems when input to the WRF-Hydro model.
   
          Args:
             parser (SafeConfigParser): parser object used to
                                        read values set in the
                                        param/config file.
             file_to_replace (string);  The fcst 0hr file that 
                                        needs to be substituted
                                        with a downscaled file
                                        from a previous model
                                        run and same valid time.
             product (string):  The name of the model product
                                (e.g. RAP, GFS, etc.)



          Returns:
             None        Creates a copy of the file and renames
                         it to be consistent with the original 
                         f000 file.

    """
    # Set the number of potential replacements we should identify
    RAP_num_tries = 6

    # Max fcst hour is set in the param config file.
    RAP_max_fcsthr = parser.get('fcsthr_max','RAP_fcsthr_max')
    GFS_max_fcsthr = parser.get('fcsthr_max','GFS_fcsthr_max')

    # Retrieve the filename portion from the full filename 
    # (ie remove the filepath portion).
    #match = re.match(r'(.*)/([0-9]{8})/i[0-9]{2}/([0-9]{8}_i[0-9]{2}_f[0-9]{3,4}_.*.nc)',file_to_replace)
    match = re.match(r'(.*)/([0-9]{8})[0-9]{2}/([0-9]{8}[0-9]{2}00.LDASIN_DOMAIN1.*)',file_to_replace)

    if match:
        base_dir = match.group(1)
        date_subdir = match.group(2)
        file_only = match.group(3) 
        print("file only from replace_fcst0hr: %s")% (file_only)
    else:
        logging.error("ERROR [replace_fcst0hr]: filename %s  is unexpected, exiting.", file_to_replace)
        sys.exit()

    # Retrieve the date, modelrun time, and fcst time  from the file name.
    (date, modelrun, fcsthr) = extract_file_info(file_only)
    
    # Typically, the valid_time = modelrun + fcsthr
    # but since we are only replacing the 0hr fcst, valid_time = modelrun
    valid_time = modelrun
    print "valid_time: %s"%valid_time

    # Get the downscaling directory from the parameter/config file, this is where 
    # we will need to search for the replacement file.
    if product == 'RAP':
        downscale_dir = parser.get('downscaling', 'RAP_downscale_output_dir')
    elif product == 'GFS':
        downscale_dir = parser.get('downscaling', 'GFS_downscale_output_dir')

    # Get the previous day's directory in the event that 
    # the previous model corresponds to the previous day's
    # data..
    prev_date_subdir = get_past_or_future_date(date)
    
    # Do some arithmetic to determine what forecast hour is needed
    # for this fcst 0hr file.

    if product == 'RAP':
       # Generate a list of possible forecast
       # hours for this valid time.
       prev = modelrun - 1
       end = prev - RAP_num_tries 
       prev_modelruns = range(prev, end, -1)

       # Construct the full file path of candidate
       # replacement data files.
       # A possible forecast with a negative value
       # indicates that we need to use the previous
       # day's model run.
       base_dir = parser.get('downscaling','RAP_downscale_output_dir')
       
       for prev_model in prev_modelruns:
         
           # Calculate the possible forecast for the previous
           # model run
           if prev_model < 0:
               # Do some math to get the model run hour.
               corrected_prev = prev_model % 24
               poss_fcst = (24 + valid_time) % corrected_prev
               # Create the full file path and name for the replacement, and 
               # if it exists, then replace the fcst 0hr file with a copy.  
               prev = (str(corrected_prev)).rjust(2,'0')
               path = base_dir + '/' + prev_date_subdir + '/i' +  prev  + '/' 
               fcst = (str(poss_fcst)).rjust(3,'0')
               file =  prev_date_subdir + '_i'+ prev + '_f' + fcst + '_RAP.nc'
               full_path = path + file

               if os.path.isfile(full_path):
                   # Make a copy
                   copy_cmd = "cp " + full_path + " " + file_to_replace
                   logging.info("copying the previous model run's file: %s",copy_cmd)      
                   os.system(copy_cmd)
                   return
               
               else:
                   logging.warning("Warning [replace_fcst0hr]: The proposed file %s does not exist", full_path) 
           else:
                
               poss_fcst = valid_time - prev_model 
  
               print "date subdir: %s"%date
               print "new model run: %s, new fcst: %s"%(prev_model, poss_fcst)
               return

       # If we are here, we didn't find any file from a previous RAP model run...
       logging.error("ERROR [replace_fcst0hr]: No previous model runs found, exiting...")
       sys.exit()
          
    elif product == 'GFS':
       base_dir = parser.get('downscaling','GFS_downscale_output_dir')

       # Generate a list of possible forecast
       # hours for this valid time. GFS has only
       # 0, 6, 12, and 18 Z model run times.
       prev = modelrun - 6
       # Use list comprehensions to generate a new list of previous
       # model runs
       prev_modelruns = range(prev, end, -6)

       if prev_modelruns < 0:
            # Use the previous day's date, but with the same valid time
     




       
def get_past_or_future_date(curr_date, num_days = -1):
    """   Determines the date in YMD format
          (i.e. YYYYMMDD) for the day before the specified date.
         
          Args:
             curr_date (string): The current date. We want to 
                                 determine the nth-previous day's 
                                 date in YMD format.
             num_days (int)    : By default, set to -1 to determine
                                 the previous day's date. Set to
                                 positive integer value for n days
                                 following the curr_date, and -n
                                 days for n days preceeding the
                                 curr_date.
          Returns:
             prev_date (string): The nth previous day's date in 
                                 YMD format (YYYYMMDD).

    """        

    curr_dt = datetime.datetime.strptime(curr_date, "%Y%m%d")
    # assign negative value to num_days so we go back by n days.
    prev_dt = curr_dt + datetime.timedelta(days=num_days)
    year = str(prev_dt.year)
    month = str(prev_dt.month)
    day = str(prev_dt.day)
    month.rjust(2,'0')
    day.rjust(2, '0')
    prev_list = [year, month, day]
    prev_date = ''.join(prev_list)
    return prev_date
    
    
    
    
    

#--------------------Defin the Workflow -------------------------

if __name__ == "__main__":
    # Replace pass with anything you wish if you want to
    # run this as a standalone program.
    pass
