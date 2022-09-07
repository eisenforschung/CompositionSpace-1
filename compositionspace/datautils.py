
import pandas as pd
import re
import os
import yaml
from tqdm.notebook import tqdm
import matplotlib.pyplot as plt
import numpy as np
from numba import jit
import pickle
import time
import h5py
import warnings
import compositionspace.paraprobe_transcoder as paraprobe_transcoder

#really check this!
pd.options.mode.chained_assignment = None

class DataPreparation:
    def __init__(self, inputfile):
        if isinstance(inputfile, dict):
            self.params = inputfile
        else:
            with open(inputfile, "r") as fin:
                params = yaml.safe_load(fin)
            self.params = params
        self.version = "1.0.0"

    def label_ions(self, pos, rrngs):
        pos['comp'] = ''
        pos['colour'] = '#FFFFFF'
        pos['nature'] = ''
        count=0;
        for n,r in rrngs.iterrows():
            count= count+1;
            pos.loc[(pos.Da >= r.lower) & (pos.Da <= r.upper),['comp','colour', 'nature']] = [r['comp'],'#' + r['colour'],count]
        
        return pos

    def atom_filter(self, x, atom_range):
        """
        Get a list of atom species and their counts
        
        Parameters
        ----------
        
        Returns
        -------
        
        Notes
        -----
        Assuming all the data
        """
        dfs = []
        for i in range(len(atom_range)):
            atom = x[x['Da'].between(atom_range['lower'][i], atom_range['upper'][i], inclusive="both")]
            dfs.append(atom)
        atom_total = pd.concat(dfs)
        count_Atom= len(atom_total['Da'])   
        return atom_total, count_Atom  


    def read_pos(self, file_name):
        """
        Read the pos file 
        
        Parameters
        ----------
        file_name: string
            Name of the input file
        
        Returns
        -------
        pos: np structured array
            The atom positions and ---- ratio
        
        Notes
        -----
        Assumptions
        
        Examples
        --------
        
        Raises
        ------
        FileNotFoundError: describe
        """
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"filename {file_name} does not exist")
        
        with open(file_name, 'rb') as f:
            dt_type = np.dtype({'names':['x', 'y', 'z', 'm'], 
                          'formats':['>f4', '>f4', '>f4', '>f4']})
            pos = np.fromfile(f, dt_type, -1)
            pos = pos.byteswap().newbyteorder()
        
        return pos

    def read_rrng(self, file_name):
        """
        Read the data 
        
        Parameters
        ----------
        
        Returns
        -------
        
        Notes
        -----
        """
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"filename {file_name} does not exist")

        patterns = re.compile(r'Ion([0-9]+)=([A-Za-z0-9]+).*|Range([0-9]+)=(\d+.\d+) +(\d+.\d+) +Vol:(\d+.\d+) +([A-Za-z:0-9 ]+) +Color:([A-Z0-9]{6})')
        ions = []
        rrngs = []
        
        with open(file_name, "r") as rf:
            for line in rf:
                m = patterns.search(line)
                if m:
                    if m.groups()[0] is not None:
                        ions.append(m.groups()[:2])
                    else:
                        rrngs.append(m.groups()[2:])
        
        ions = pd.DataFrame(ions, columns=['number','name'])
        ions.set_index('number',inplace=True)
        rrngs = pd.DataFrame(rrngs, columns=['number','lower','upper','vol','comp','colour'])
        rrngs.set_index('number',inplace=True) 
        rrngs[['lower','upper','vol']] = rrngs[['lower','upper','vol']].astype(float)
        rrngs[['comp','colour']] = rrngs[['comp','colour']].astype(str)
        return ions, rrngs

    def read_apt(self, file_name):
        """
        Read the apt file 
        
        Parameters
        ----------
        file_name: string
            Name of the input file
        
        Returns
        -------
        pos: np structured array
            The atom positions and ---- ratio
        
        Notes
        -----
        Assumptions
        
        Examples
        --------
        
        Raises
        ------
        FileNotFoundError: describe
        """
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"filename {file_name} does not exist")
        
        apt = paraprobe_transcoder.paraprobe_transcoder(file_name)
        apt.read_cameca_apt()
        POS = apt.Position
        MASS = apt.Mass
        POS_MASS = np.concatenate((POS,MASS),axis = 1)
        return POS_MASS

    def read_apt_to_df(self):
        """
        Read the data 
        
        Parameters
        ----------
        
        Returns
        -------
        
        Notes
        -----
        """
        df_Mass_POS_lst = []
        file_name_lst=[]
        ions = None 
        rrngs = None

        pbar = tqdm(os.listdir(self.params["input_path"]), desc="Reading files")
        for filename in pbar:
            if filename.lower().endswith(".pos"):
                path = os.path.join(self.params["input_path"], filename)            
                pos = self.read_pos(path)
                df_POS_MASS = pd.DataFrame({'x':pos['x'],'y': pos['y'],'z': pos['z'],'Da': pos['m']})
                df_Mass_POS_lst.append(df_POS_MASS)
                file_name_lst.append(filename)

            if filename.endswith(".apt"):
                path = os.path.join(self.params["input_path"], filename)
                POS_MASS = self.read_apt(path) 
                df_POS_MASS = pd.DataFrame(POS_MASS, columns = ["x","y","z","Da"])
                df_Mass_POS_lst.append(df_POS_MASS)
                file_name_lst.append(filename)

            if filename.lower().endswith(".rrng"):
                path = os.path.join(self.params["input_path"], filename) 
                ions,rrngs = self.read_rrng(path)
                
        return (df_Mass_POS_lst, file_name_lst, ions, rrngs) 



    def chunkify_apt_df(self):
        """
        Cut the data into specified portions
        
        Parameters
        ----------
        
        Returns
        -------
        
        Notes
        -----
        """
        #df_lst, files, ions, rrngs= read_apt_to_df(folder)
        df_lst, files, ions, rrngs= self.read_apt_to_df()

        filestrings = []
        prefix = self.params['output_path']
        
        for idx, file in enumerate(files):
            org_file = df_lst[idx]
            atoms_spec = []
            c = np.unique(rrngs.comp.values)
            for i in range(len(c)):
                range_element = rrngs[rrngs['comp']=='{}'.format(c[i])]
                total, count = self.atom_filter(org_file, range_element)
                total["spec"] = [x for x in range(len(total))]
                atoms_spec.append(total)

            df_atom_spec = pd.concat(atoms_spec)
            sorted_df = df_atom_spec.sort_values(by=['z'])

            filestring = "file_{}_large_chunks_arr.h5".format(file.replace(".","_"))
            filestring = os.path.join(prefix, filestring)
            filestrings.append(filestring)

            hdf = h5py.File(filestring, "w")
            group1 = hdf.create_group("group_xyz_Da_spec")
            group1.attrs["columns"] = ["x","y","z","Da","spec"]
            group1.attrs["spec_name_order"] = list(c)
            sublength_x= abs((max(sorted_df['z'])-min(sorted_df['z']))/self.params["n_big_slices"])
            
            start = min(sorted_df['z'])
            end = min(sorted_df['z']) + sublength_x
            
            pbar = tqdm(range(self.params["n_big_slices"]), desc="Creating chunks")
            for i in pbar:
                temp = sorted_df[sorted_df['z'].between(start, end, inclusive="both")]
                group1.create_dataset("chunk_{}".format(i), data = temp.values)
                start += sublength_x
                end += sublength_x 
            hdf.close()                

        self.chunk_files = filestrings 

        
    def get_voxels(self):
        """
        
        
        Parameters
        ----------
        
        Returns
        -------
        
        Notes
        -----
        """
        filestrings = []
        prefix = self.params['output_path']
        size = self.params["voxel_size"]

        for filename in self.chunk_files:
            hdfr = h5py.File(filename, "r")
            filestring = filename.replace("large", "small")
            #filestring = os.path.join(prefix, filestring)
            filestrings.append(filestring)

            with h5py.File(filestring, "w") as hdfw:
                group_r = hdfr.get("group_xyz_Da_spec")
                group_keys = list(group_r.keys())
                columns_r = list(list(group_r.attrs.values())[0])

                group1 = hdfw.create_group("0")
                prev_attri =list(list(group_r.attrs.values())[0])
                prev_attri.append("vox_file")
                group1.attrs["columns"] =  prev_attri
                group1.attrs["spec_name_order"] = list(list(group_r.attrs.values())[1])

                name_sub_file = 0
                step = 0
                m=0

                pbar = tqdm(group_keys, desc="Getting Voxels")
                for key in pbar:
                    read_array = np.array(group_r.get(key))
                    s= pd.DataFrame(data = read_array, columns =  columns_r)
                    x_min = round(min(s['x']))
                    x_max = round(max(s['x']))
                    y_min = round(min(s['y']))
                    y_max = round(max(s['y']))
                    z_min = round(min(s['z']))
                    z_max = round(max(s['z']))   
                    p=[]
                    x=[]

                    for i in range(z_min, z_max, size):
                        cubic = s[s['z'].between(i, i+size, inclusive="both")]
                        for j in range(y_min, y_max, size):
                            p = cubic[cubic['y'].between(j, j+size, inclusive="both")]
                            for k in range(x_min, x_max, size):
                                x = p[p['x'].between(k, k+size, inclusive="both")]
                                if len(x['x'])>20:
                                    #warnings.warn("I am running some code with hardcoded numbers. Really recheck what's up here!")
                                    name ='cubes_z{}_x{}_y{}'.format(i,j,k).replace("-","m")
                                    if step>99999:
                                        step=0
                                        m=m+1
                                        group1 = hdfw.create_group("{}".format(100000*m))

                                    x["vox_file"] = [name_sub_file for n_file in range(len(x))]
                                    group1.create_dataset("{}".format(name_sub_file), data = x.values)
                                    name_sub_file = name_sub_file+1
                                    step=step+1
                group1 = hdfw.get("0")
                group1.attrs["total_voxels"]="{}".format(name_sub_file)

        self.voxel_files = filestrings
                    
    def calculate_voxel_composition(self, fileindex=0, outfilename="3Vox_ratios_filenames_num_MR_Grp.h5"):
        """
        This works only a single filename; check
        """
        vox_ratio_files = []

        for voxel_file in self.voxel_files:
            outfilename = voxel_file.replace("small_chunk", "vox_ratio")
            vox_ratio_files.append(outfilename)
            small_chunk_file_name = self.voxel_files[fileindex]
            hdf_sm_r = h5py.File(small_chunk_file_name, "r")
            group = hdf_sm_r.get("0")
                
            #SRM: changed to indice 2 for the first one. Please check.
            total_voxels =list(list(group.attrs.values())[2])
            spec_lst_len = len(list(list(group.attrs.values())[2]))

            items = list(hdf_sm_r.items())
            item_lst = []
            ### CHECK THESE NUMBERS!
            for item in range(len(items)):
                item_lst.append([100000*(item), 100000*(item+1)])
            item_lst = np.array(item_lst)
            
            
            total_voxels_int =""
            for number in total_voxels:
                total_voxels_int = total_voxels_int + number

            total_voxels_int = int(total_voxels_int)

            files = [file_num for file_num in range(total_voxels_int)]
            
            
            spec_names =  np.arange(spec_lst_len)
            dic_ratios = {}
            for spec_name in spec_names:
                dic_ratios["{}".format(spec_name)] = []

            dic_ratios["Total_no"]=[]
            dic_ratios["file_name"]=[]
            dic_ratios["vox"] = []

            ratios = []
            f_count = 0
            pbar = tqdm(files, desc="Calculating voxel composition")
            for filename in pbar:
                group = np.min(item_lst[[filename in range(j[0],j[1]) for j in item_lst]])
                arr = np.array(hdf_sm_r.get("{}/{}".format(group,filename))[:,4])
                N_x = len(arr)

                for spec in (spec_names):
                    ratio = (len(np.argwhere(arr==spec)))/N_x
                    dic_ratios["{}".format(spec)].append(ratio)

                dic_ratios["file_name"].append(filename)
                dic_ratios["vox"].append(f_count)
                dic_ratios["Total_no"].append(N_x)
                f_count = f_count+1
                
            df = pd.DataFrame.from_dict(dic_ratios)

            
            with h5py.File(outfilename, "w") as hdfw:
                hdfw.create_dataset("vox_ratios", data =df.drop("file_name", axis = 1).values )
                hdfw.attrs["what"] = ["All the Vox ratios for a given APT smaple"]
                hdfw.attrs["howto_Group_name"] = ["Group_sm_vox_xyz_Da_spec/"]
                hdfw.attrs["columns"]= ['0.0', '1.0', '2.0', '3.0', '4.0', 'Total_no', 'vox']

            hdf_sm_r.close()
        self.voxel_ratio_files = vox_ratio_files
    
    

