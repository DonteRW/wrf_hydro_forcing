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
                                   of the regridded file.  If the data
                                   product is GFS or RAP and it is the
                                   fcst 0hr file, then just create an
                                   empty file that follows the naming
                                   convention of a regridded file.

    """


    # Retrieve the values from the parm/config file
    # which are needed to invoke the regridding 
    # scripts.
    product = product_name.upper()
    ncl_exec = parser.get('exe', 'ncl_exe')


    if product == 'HRRR':
       wgt_file = parser.get('regridding', 'HRRR_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'HRRR_data')
       regridding_exec = parser.get('exe', 'HRRR_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','HRRR_output_dir')
       dst_grid_name = parser.get('regridding','HRRR_dst_grid_name')
    elif product == 'MRMS':
       wgt_file = parser.get('regridding', 'MRMS_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'MRMS_data')
       regridding_exec = parser.get('exe', 'MRMS_regridding_exe')
       #data_files_to_process = get_filepaths(data_dir)   
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','MRMS_output_dir')
       dst_grid_name = parser.get('regridding','MRMS_dst_grid_name')
    elif product == 'NAM':
       wgt_file = parser.get('regridding', 'NAM_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'NAM_data')
       regridding_exec = parser.get('exe', 'NAM_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','NAM_output_dir')
       dst_grid_name = parser.get('regridding','NAM_dst_grid_name')
    elif product == 'GFS':
       wgt_file = parser.get('regridding', 'GFS_wgt_bilinear')
       data_dir =  parser.get('data_dir', 'GFS_data')
       regridding_exec = parser.get('exe', 'GFS_regridding_exe')
       #Values needed for running the regridding script
       output_dir_root = parser.get('regridding','GFS_output_dir')
       dst_grid_name = parser.get('regridding','GFS_dst_grid_name')
    elif product == 'RAP':
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
        (date,model,fcsthr) = extract_file_info(file_to_regrid)  
        data_file_to_regrid= data_dir + "/" + date + "/" + file_to_regrid 
        (date,model,fcsthr) = extract_file_info(file_to_regrid)  
        (subdir_file_path,hydro_filename) = \
            create_output_name_and_subdir(product,data_file_to_regrid,data_dir)
        output_file_dir = output_dir_root + "/" + subdir_file_path
        mkdir_p(output_file_dir)
        outdir_param = "'outdir=" + '"' + output_file_dir + '"' + "' " 
        regridded_file = output_file_dir + "/" +  hydro_filename
        # Create an empty f0 file for now.
        with open(regridded_file,'a'):
            os.utime(regridded_file,None)
        return regridded_file  
        
    else:

        # Generate the key-value pairs for 
        # input to the regridding script.
        # The key-value pairs for the input should look like: 
        #  'srcfilename="/d4/hydro-dm/IOC/data/HRRR/20150723_i23_f010_HRRR.grb2"' 
        #  'wgtFileName_in=
        #     "d4/hydro-dm/IOC/weighting/HRRR1km/HRRR2HYDRO_d01_weight_bilinear.nc"'
        #  'dstGridName="/d4/hydro-dm/IOC/data/geo_dst.nc"' 
        #  'outdir="/d4/hydro-dm/IOC/regridded/HRRR/2015072309"'
        #  'outFile="201507241900.LDASIN_DOMAIN1.nc"' 
       
        (date,model,fcsthr) = extract_file_info(file_to_regrid)  
        data_file_to_regrid= data_dir + "/" + date + "/" + file_to_regrid 
        srcfilename_param =  "'srcfilename=" + '"' + data_file_to_regrid +  \
                                 '"' + "' "
        wgtFileName_in_param =  "'wgtFileName_in = " + '"' + wgt_file + \
                                    '"' + "' "
        dstGridName_param =  "'dstGridName=" + '"' + dst_grid_name + '"' + "' "
    
        # Create the output filename following the 
        # naming convention for the WRF-Hydro model 
        (subdir_file_path,hydro_filename) = \
            create_output_name_and_subdir(product,data_file_to_regrid,data_dir)
       
        # Create the full path to the output directory
        # and assign it to the output directory parameter
        output_file_dir = output_dir_root + "/" + subdir_file_path
        mkdir_p(output_file_dir)
        outdir_param = "'outdir=" + '"' + output_file_dir + '"' + "' " 
        regridded_file = output_file_dir + "/" + hydro_filename

        if product == "HRRR" or product == "NAM" \
           or product == "GFS" or product == "RAP":
           full_output_file = output_file_dir + "/"  
           # Create the new output file subdirectory
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
    """Generates the file names in a directory tree
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
    """Creates the full filename for the regridded data which ties-in
       to the WRF-Hydro Model expected input: 
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
        match =  re.match(r'.*/([0-9]{8})_i([0-9]{2})_f([0-9]{3,4}).*',filename)
        if match:
            year_month_day = match.group(1)
            init_hr = int(match.group(2))
            fcst_hr = int(match.group(3))
            valid_time = fcst_hr + init_hr
            init_hr_str = (str(init_hr)).rjust(2,'0')
            year_month_day_subdir = year_month_day + init_hr_str
        else:
            logging.error("ERROR [create_output_name_and_subdir]: %s has an unexpected name." ,filename) 
            sys.exit()

    elif product == 'MRMS':
        match = re.match(r'.*([0-9]{8})_([0-9]{2}).*',filename) 
        if match:
           year_month_day = match.group(1)
           init_hr =  match.group(2)

           # Radar data- not a model, therefore no forecast
           # therefore valid time is the init time
           valid_time = int(init_hr)
           year_month_day_subdir = year_month_day + init_hr 
        else:
           logging.error("ERROR: MRMS data filename %s \
                          has an unexpected file name.",\
                          filename) 
           sys.exit()

   
    if valid_time >= 24:
        num_days_ahead =  valid_time/24
        # valid time in 24 hour time
        valid_time_str =  str(valid_time%24)
        valid_time_corr = valid_time_str.rjust(2,'0')
        updated_date = get_past_or_future_date(year_month_day, num_days_ahead)
        # Assemble the filename and the full output directory path
        hydro_filename = updated_date + valid_time_corr + "00.LDASIN_DOMAIN1.nc" 
    else:
        # Assemble the filename and the full output directory path
        valid_time_str = (str(valid_time)).rjust(2,'0')
        hydro_filename = year_month_day + valid_time_str + "00.LDASIN_DOMAIN1.nc" 

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
    """Performs downscaling of data by calling the necessary
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
        data_to_downscale_dir = parser.get('downscaling','HRRR_data_to_downscale')
        hgt_data_file = parser.get('downscaling','HRRR_hgt_data')
        geo_data_file = parser.get('downscaling','HRRR_geo_data')
        downscale_output_dir = parser.get('downscaling', 'HRRR_downscale_output_dir')
        downscale_exe = parser.get('exe', 'HRRR_downscaling_exe')
    elif product == 'NAM':
        data_to_downscale_dir = parser.get('downscaling','NAM_data_to_downscale')
        hgt_data_file = parser.get('downscaling','NAM_hgt_data')
        geo_data_file = parser.get('downscaling','NAM_geo_data')
        downscale_output_dir = parser.get('downscaling', 'NAM_downscale_output_dir')
        downscale_exe = parser.get('exe', 'NAM_downscaling_exe')
    elif product == 'GFS':
        data_to_downscale_dir = parser.get('downscaling','GFS_data_to_downscale')
        hgt_data_file = parser.get('downscaling','GFS_hgt_data')
        geo_data_file = parser.get('downscaling','GFS_geo_data')
        downscale_output_dir = parser.get('downscaling', 'GFS_downscale_output_dir')
        downscale_exe = parser.get('exe', 'GFS_downscaling_exe')
    elif product == 'RAP':
        data_to_downscale_dir = parser.get('downscaling','RAP_data_to_downscale')
        hgt_data_file = parser.get('downscaling','RAP_hgt_data')
        geo_data_file = parser.get('downscaling','RAP_geo_data')
        downscale_output_dir = parser.get('downscaling', 'RAP_downscale_output_dir')
        downscale_exe = parser.get('exe', 'RAP_downscaling_exe')
    else:
        logging.info("Requested downscaling of unsupported data product %s", product)
 
     
    # If this is a fcst 0hr file and is either RAP or GFS, then search for
    # a suitable replacement since this file will have one or more 
    # missing variable(s).
    # Otherwise, proceed with creating the request to downscale.
 
    if substitute_fcst:
        # Find another downscaled file from the previous model/
        # init time with the same valid time as this file, then 
        # copy to this fcst 0hr file.
        replace_fcst0hr(parser, file_to_downscale,product)

    else:
        # Downscale as usual
        match = re.match(r'(.*)([0-9]{10})/([0-9]{8}([0-9]{2})00.LDASIN_DOMAIN1.*)',file_to_downscale)
        if match:
            yr_month_day_init = match.group(2)
            regridded_file = match.group(3)
            valid_hr = match.group(4)
        else:
            logging.error("ERROR: regridded file's name: %s is an unexpected format",\
                               file_to_downscale)
            sys.exit() 
   
        full_downscaled_dir = downscale_output_dir + "/" + yr_month_day_init  
        full_downscaled_file = full_downscaled_dir + "/" +  regridded_file

        # Create the full output directory for the downscaled data if it doesn't 
        # already exist. 
        mkdir_p(full_downscaled_dir) 
    
    
        # Create the key-value pairs that make up the
        # input for the NCL script responsible for
        # the downscaling.
        input_file1_param = "'inputFile1=" + '"' + hgt_data_file + '"' + "' "
        input_file2_param = "'inputFile2=" + '"' + geo_data_file + '"' + "' "
        input_file3_param = "'inputFile3=" + '"' + file_to_downscale + '"' + "' "
        lapse_file_param =  "'lapseFile=" + '"' + lapse_rate_file + '"' + "' "
        output_file_param = "'outFile=" + '"' + full_downscaled_file + '"' + "' "
        downscale_params =  input_file1_param + input_file2_param + \
                  input_file3_param + lapse_file_param +  output_file_param 
        downscale_cmd = ncl_exec + " " + downscale_params + " " + downscale_exe
    
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



def layer_data(parser, first_data, second_data, first_data_product, second_data_product):
    """Invokes the NCL script, combine.ncl
       to layer/combine two files:  a primary and secondary
       file (with identical date/time, model run time, and
       forecast time) are found by iterating through a list
       of primary files and determining if the corresponding
       secondary file exists.


        Args:
              parser (ConfigParser):  The parser to the config/parm
                                      file containing all the defined
                                      values.
              first_data (string):  The name of the first data file
 
              second_data (string): The name of the second data file
                                    (e.g. HRRR or RAP)
            
              first_data_product (string): The product type of the 
                                           first 

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
                             secondary file")
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
        forecast hour (UTC) from the (raw) input 
        data file name (i.e. data that hasn't been
        regridded, downscaled,etc.).

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
    match = re.match(r'.*([0-9]{8})_i([0-9]{2})_f([0-9]{3,4}).*', input_file)

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
       fcst_hr = int(0)
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
        
      
    if int(fcsthr) >= fcst_max:
        logging.info("Skip file, fcst hour %d is outside of fcst max %d",fcsthr,fcst_max)
        return False
    else:
        return True






def replace_fcst0hr(parser, file_to_replace, product):
    """ There are some missing variables in the 0hr forecast
          for RAP and GFS (such as precipitation
          and radiation fields), which cause
          problems when input to the WRF-Hydro model.
          Substitute these files with downscaled data 
          file from the previous model run/init time:
          YYYYMMDDHH, where HH is the model/init time.
          The file associated with this previous model/init
          time is readily identified as a file with the same name 
          in an earlier model/init run's subdirectory (i.e. previous
          HH = HH-1).
   
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
             None        Creates a copy of the file and saves
                         it to the appropriate directory:
                         YYYYMMDDHH, where HH is the model/init time.


    """
    # Retrieve the date, model time,valid time, and filename from the full filename 
    logging.info("INFO[replace_fcst0hr]: file to replace=%s", file_to_replace)
    match = re.match(r'(.*)/([0-9]{8})([0-9]{2})/([0-9]{8}([0-9]{2})00.LDASIN_DOMAIN1.nc)',file_to_replace)
    if match:
        base_dir = match.group(1)
        curr_date = match.group(2)
        model_time = int(match.group(3))
        file_only = match.group(4) 
        valid_time = int(match.group(5))
        logging.info("file only from replace_fcst0hr: %s",file_only)
    else:
        logging.error("ERROR[replace_fcst0hr]: filename %s  is unexpected, exiting.", file_to_replace)
        sys.exit()


    # Get the previous directory corresponding to the previous
    # model run/init time.
    if model_time == 0:
        # Use the previous day's last model run
        # and date.
        prev_model_time = 23
        date = get_past_or_future_date(curr_date,-1)
        # Pad the model time with zeroes.
        prev_model_time_str = (str(prev_model_time)).rjust(2,'0')

    else:
        prev_model_time = model_time - 1
        prev_model_time_str = (str(prev_model_time)).rjust(2,'0')
        date = curr_date


    if product == 'RAP':
        # Create the full file path and name to create the directory of
        # the previous model run/init time (i.e. YYYYMMDDH'H', 
        # where H'H' is the previous model run/init).
        # In this directory, search for the fcst 0hr file with the same name.  If it 
        # exists, copy it over to the YYYYMMDDHH directory of the
        # fcst 0hr file in the downscaling output directory.  
        base_dir = parser.get('downscaling','RAP_downscale_output_dir')
        full_path = base_dir + '/' + date + prev_model_time_str + "/" + \
                    file_only
        logging.info("INFO [replace_fcst0hr]: full path = %s", full_path)
        if os.path.isfile(full_path):
            # Make a copy
            file_dir_fcst0hr = base_dir + "/" + date + (str(model_time)).rjust(2,'0') 
            # Make the directory for the downscaled fcst 0hr 
            mkdir_p(file_dir_fcst0hr)
            file_path_to_replace = file_dir_fcst0hr + "/" + file_only
            copy_cmd = "cp " + full_path + " " + file_path_to_replace
            logging.info("copying the previous model run's file: %s",copy_cmd)      
            os.system(copy_cmd)
            return
        else:
            # If we are here, we didn't find any file from a previous RAP model run...
            logging.error("ERROR: No previous model runs found, exiting...")
            sys.exit()
            logging.info("INFO: [replace_fcst0hr] SHOULD NEVER SEE THIS") 
          
    elif product == 'GFS':
       base_dir = parser.get('downscaling','GFS_downscale_output_dir')





       
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
    prev_dt = curr_dt + datetime.timedelta(days=num_days)
    year = str(prev_dt.year)
    month = str(prev_dt.month)
    day = str(prev_dt.day)
    month.rjust(2,'0')
    day.rjust(2, '0')
    prev_list = [year, month, day]
    prev_date = ''.join(prev_list)
    return prev_date
    
    
    
    
    

#--------------------Define the Workflow -------------------------

if __name__ == "__main__":
    # Replace pass with anything you wish if you want to
    # run this as a standalone program.
    pass
