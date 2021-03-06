#!/usr/bin/env python

#    Various functions for TFCE_mediation
#    Copyright (C) 2016  Tristram Lett, Lea Waller

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.


import os
import numpy as np
import nibabel as nib
import math
import sys
import struct
from scipy.stats import linregress
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.patches as mpatches
from time import time


from tfce_mediation.cynumstats import calc_beta_se, resid_covars, cy_lin_lstsqr_mat

# Creation of adjacencty sets for TFCE connectivity
def create_adjac_vertex(vertices,faces): # basic version
	adjacency = [set([]) for i in range(vertices.shape[0])]
	for i in range(faces.shape[0]):
		adjacency[faces[i, 0]].add(faces[i, 1])
		adjacency[faces[i, 0]].add(faces[i, 2])
		adjacency[faces[i, 1]].add(faces[i, 0])
		adjacency[faces[i, 1]].add(faces[i, 2])
		adjacency[faces[i, 2]].add(faces[i, 0])
		adjacency[faces[i, 2]].add(faces[i, 1])
	return adjacency

def create_adjac_voxel (data_index,data_mask,num_voxel, dirtype=26): # default is 26 directions
	ind=np.where(data_index)
	dm=np.zeros_like(data_mask)
	x_dim,y_dim,z_dim=data_mask.shape
	adjacency = [set([]) for i in range(num_voxel)]
	label=0
	for x,y,z in zip(ind[0],ind[1],ind[2]):
		dm[x,y,z] = label
		label += 1
	for x,y,z in zip(ind[0],ind[1],ind[2]):
		xMin=max(x-1,0)
		xMax=min(x+1,x_dim-1)
		yMin=max(y-1,0)
		yMax=min(y+1,y_dim-1)
		zMin=max(z-1,0)
		zMax=min(z+1,z_dim-1)
		local_area = dm[xMin:xMax+1,yMin:yMax+1,zMin:zMax+1]
		if int(dirtype)==6:
			if local_area.shape!=(3,3,3): # check to prevent calculating adjacency at walls
				local_area = dm[x,y,z] 
			else:
				local_area = local_area * np.array([0,0,0,0,1,0,0,0,0,0,1,0,1,1,1,0,1,0,0,0,0,0,1,0,0,0,0]).reshape(3,3,3)
		cV = int(dm[x,y,z])
		for j in local_area[local_area>0]:
			adjacency[cV].add(int(j))
	return adjacency

#writing statistics images

def write_vertStat_img(statname, vertStat, outdata_mask, affine_mask, surf, hemi, bin_mask, TFCEfunc, all_vertex, density_corr = 1, TFCE = True):
	vertStat_out=np.zeros(all_vertex).astype(np.float32, order = "C")
	vertStat_out[bin_mask] = vertStat
	if TFCE:
		vertStat_TFCE = np.zeros_like(vertStat_out).astype(np.float32, order = "C")
		TFCEfunc.run(vertStat_out, vertStat_TFCE)
		outdata_mask[:,0,0] = vertStat_TFCE * (vertStat[np.isfinite(vertStat)].max()/100) * density_corr
		fsurfname = "%s_%s_%s_TFCE.mgh" % (statname,surf,hemi)
		os.system("echo %s_%s_%s,%f >> max_TFCE_contrast_values.csv" % (statname,surf,hemi, outdata_mask[np.isfinite(outdata_mask[:,0,0])].max()))
		nib.save(nib.freesurfer.mghformat.MGHImage(outdata_mask,affine_mask),fsurfname)
	outdata_mask[:,0,0] = vertStat_out
	fsurfname = "%s_%s_%s.mgh" % (statname,surf,hemi)
	nib.save(nib.freesurfer.mghformat.MGHImage(outdata_mask,affine_mask),fsurfname)

def write_voxelStat_img(statname, voxelStat, out_path, data_index, affine, TFCEfunc, imgext = '.nii.gz', TFCE = True):
	if TFCE:
		voxelStat_out = voxelStat.astype(np.float32, order = "C")
		voxelStat_TFCE = np.zeros_like(voxelStat_out).astype(np.float32, order = "C")
		TFCEfunc.run(voxelStat_out, voxelStat_TFCE)
		out_path[data_index] = voxelStat_TFCE * (voxelStat_out.max()/100)
		nib.save(nib.Nifti1Image(out_path,affine),"%s_TFCE%s" % (statname, imgext))
		os.system("echo %s,%f >> max_TFCE_contrast_values.csv" % (statname,out_path.max()))
	out_path[data_index] = voxelStat
	nib.save(nib.Nifti1Image(out_path,affine),"%s%s" % (statname, imgext))

#writing max TFCE values from permutations

def write_perm_maxTFCE_vertex(statname, vertStat, num_vertex, bin_mask_lh, bin_mask_rh, calcTFCE_lh,calcTFCE_rh, density_corr_lh = 1, density_corr_rh = 1):
	vertStat_out_lh=np.zeros(bin_mask_lh.shape[0]).astype(np.float32, order = "C")
	vertStat_out_rh=np.zeros(bin_mask_rh.shape[0]).astype(np.float32, order = "C")
	vertStat_TFCE_lh = np.zeros_like(vertStat_out_lh).astype(np.float32, order = "C")
	vertStat_TFCE_rh = np.zeros_like(vertStat_out_rh).astype(np.float32, order = "C")
	vertStat_out_lh[bin_mask_lh] = vertStat[:num_vertex]
	vertStat_out_rh[bin_mask_rh] = vertStat[num_vertex:]
	calcTFCE_lh.run(vertStat_out_lh, vertStat_TFCE_lh)
	calcTFCE_rh.run(vertStat_out_rh, vertStat_TFCE_rh)
	max_lh = vertStat_TFCE_lh[np.isfinite(vertStat_TFCE_lh)] * (vertStat_out_lh[np.isfinite(vertStat_out_lh)].max()/100) * density_corr_lh
	max_rh = vertStat_TFCE_rh[np.isfinite(vertStat_TFCE_rh)] * (vertStat_out_rh[np.isfinite(vertStat_out_rh)].max()/100) * density_corr_rh
	maxTFCE = np.array([max_lh.max(),max_rh.max()]).max()
	os.system("echo %.4f >> perm_%s_TFCE_maxVertex.csv" % (maxTFCE,statname))

def write_perm_maxTFCE_voxel(statname, voxelStat, TFCEfunc):
	voxelStat_out = voxelStat.astype(np.float32, order = "C")
	voxelStat_TFCE = np.zeros_like(voxelStat_out).astype(np.float32, order = "C")
	TFCEfunc.run(voxelStat_out, voxelStat_TFCE)
	maxval = voxelStat_TFCE.max() * (voxelStat_out.max()/100)
	os.system("echo %1.4f >> perm_%s_TFCE_maxVoxel.csv" % (maxval,statname))

#calculating Sobel Z statistics using T stats

def calc_sobelz(medtype, pred_x, depend_y, merge_y, n, num_vertex, alg = "aroian"):
	if medtype == 'I':
		PathA_beta, PathA_se = calc_beta_se(pred_x,merge_y,n,num_vertex)
		PathB_beta, PathB_se = calc_beta_se(np.column_stack([pred_x,depend_y]),merge_y,n,num_vertex)
		PathA_se = PathA_se[1]
		PathB_se = PathB_se[1]
	elif medtype == 'M':
		PathA_beta, PathA_se = calc_beta_se(pred_x,merge_y,n,num_vertex)
		PathB_beta, PathB_se = calc_beta_se(np.column_stack([depend_y,pred_x]),merge_y,n,num_vertex)
		PathA_se = PathA_se[1]
		PathB_se = PathB_se[1]
	elif medtype == 'Y':
		PathA_beta, _, _, _, PathA_se = linregress(pred_x, depend_y)
		PathB_beta, PathB_se = calc_beta_se(np.column_stack([depend_y,pred_x]),merge_y,n,num_vertex)
		PathB_se = PathB_se[1]
	else:
		print("Invalid mediation type")
		exit()
	ta = PathA_beta/PathA_se
	tb = PathB_beta/PathB_se
	if alg == 'aroian':
		#Aroian variant
		SobelZ = 1/np.sqrt((1/(tb**2))+(1/(ta**2))+(1/(ta**2*tb**2)))
	elif alg == 'sobel':
		#Sobel variant
		SobelZ = 1/np.sqrt((1/(tb**2))+(1/(ta**2)))
	elif alg == 'goodman':
		#Goodman variant
		SobelZ = 1/np.sqrt((1/(tb**2))+(1/(ta**2))-(1/(ta**2*tb**2)))
	else:
		print("Unknown indirect test algorithm")
		exit()
	return SobelZ

### tm_maths functions ###


def converter_try(vals):
	resline = []
	try:
		resline.append(int(vals))
		num_check=1
	except ValueError:
		try:
			resline.append(float(vals))
			num_check=1
		except ValueError:
			resline.append(vals)
			num_check=0
	return num_check

def loadnifti(imagename):
	if os.path.exists(imagename): # check if file exists
		if imagename.endswith('.nii.gz'):
			os.system("zcat %s > temp.nii" % imagename)
			img = nib.load('temp.nii')
			img_data = img.get_data()
			os.system("rm temp.nii")
		else:
			img = nib.load(imagename)
			img_data = img.get_data()
	else:
		print("Cannot find input image: %s" % imagename)
		exit()
	return (img,img_data)

def loadmgh(imagename):
	if os.path.exists(imagename): # check if file exists
		img = nib.freesurfer.mghformat.load(imagename)
		img_data = img.get_data()
	else:
		print("Cannot find input image: %s" % imagename)
		exit()
	return (img,img_data)

def loadtwomgh(imagename):
	if os.path.exists(imagename): # check if file exists
		lh_imagename = imagename
		rh_imagename = 'rh.%s' % (imagename.split('lh.',1)[1])
		if os.path.exists(rh_imagename): # check if file exists
			# truncated both hemispheres into a single array
			lh_img = nib.freesurfer.mghformat.load(lh_imagename)
			lh_img_data = lh_img.get_data()
			lh_mean_data = np.mean(np.abs(lh_img_data),axis=3)
			lh_mask_index = (lh_mean_data != 0)
			rh_img = nib.freesurfer.mghformat.load(rh_imagename)
			rh_img_data = rh_img.get_data()
			rh_mean_data = np.mean(np.abs(rh_img_data),axis=3)
			rh_mask_index = (rh_mean_data != 0)
			lh_img_data_trunc = lh_img_data[lh_mask_index]
			rh_img_data_trunc = rh_img_data[rh_mask_index]
			img_data_trunc = np.vstack((lh_img_data_trunc,rh_img_data_trunc))
			midpoint = lh_img_data_trunc.shape[0]
		else:
			print("Cannot find input image: %s" % rh_imagename)
			exit()
	else:
		print("Cannot find input image: %s" % imagename)
		exit()
	return (img_data_trunc, midpoint, lh_img, rh_img, lh_mask_index, rh_mask_index)

def savenifti(imgdata, img, index, imagename):
	outdata = imgdata.astype(np.float32, order = "C")
	if imgdata.ndim == 2:
		imgout = np.zeros((img.shape[0],img.shape[1],img.shape[2],outdata.shape[1]))
	elif imgdata.ndim == 1:
		imgout = np.zeros((img.shape[0],img.shape[1],img.shape[2]))
	else:
		print('error')
	imgout[index]=outdata
	nib.save(nib.Nifti1Image(imgout.astype(np.float32, order = "C"),img.affine),imagename)

def savemgh(imgdata, img, index, imagename):
	outdata = imgdata.astype(np.float32, order = "C")
	if imgdata.ndim == 2:
		imgout = np.zeros((img.shape[0],img.shape[1],img.shape[2],outdata.shape[1]))
	elif imgdata.ndim == 1:
		imgout = np.zeros((img.shape[0],img.shape[1],img.shape[2]))
	else:
		print('error')
	imgout[index]=outdata
	nib.save(nib.freesurfer.mghformat.MGHImage(imgout.astype(np.float32, order = "C"),img.affine),imagename)

#find nearest permuted TFCE max value that corresponse to family-wise error rate 
def find_nearest(array,value,p_array):
	idx = np.searchsorted(array, value, side="left")
	if idx == len(p_array):
		return p_array[idx-1]
	elif math.fabs(value - array[idx-1]) < math.fabs(value - array[idx]):
		return p_array[idx-1]
	else:
		return p_array[idx]

# Z standardize or whiten
def zscaler(X, axis=0, w_mean=True, w_std=True):
	data = np.copy(X)
	if w_mean:
		data -= np.mean(data, axis)
	if w_std:
		data /= np.std(data, axis)
	return data

# orthonormalizaiton with QR factorization
def gram_schmidt_orthonorm(X, columns=True):
	if columns:
		Q, _ = np.linalg.qr(X)
	else:
		Q, _ = np.linalg.qr(X.T)
		Q = Q.T
	return Q

#max-min standardization
def minmaxscaler(X, axis=0):
	X = (X - X.min(axis)) / (X.max(axis) - X.min(axis))
	return X


### surface conversion tools ###

def check_outname(outname):
	if os.path.exists(outname):
		outpath,outname = os.path.split(outname)
		if not outpath:
			outname = ("new_%s" % outname)
		else:
			outname = ("%s/new_%s" % (outpath,outname))
		print("Output file aleady exists. Renaming output file to %s" % outname)
		if os.path.exists(outname):
			print("%s also exists. Overwriting the file." % outname)
			os.remove(outname)
	return outname

def file_len(fname):
	with open(fname) as f:
		for i, l in enumerate(f):
			pass
	return i + 1

# not used
def computeNormals(v, f):
	v_ = v[f]
	fn = np.cross(v_[:, 1] - v_[:, 0], v_[:, 2] - v_[:,0])
	fs = np.sqrt(np.sum((v_[:, [1, 2, 0], :] - v_) ** 2, axis = 2))
	fs_ = np.sum(fs, axis = 1) / 2 # heron's formula
	fa = np.sqrt(fs_ * (fs_ - fs[:, 0]) * (fs_ - fs[:, 1]) * (fs_ - fs[:, 2]))[:, None]
	vn = np.zeros_like(v, dtype = np.float32)
	vn[f[:, 0]] += fn * fa # weight by area
	vn[f[:, 1]] += fn * fa
	vn[f[:, 2]] += fn * fa
	vlen = np.sqrt(np.sum(vn ** 2, axis = 1))[np.any(vn != 0, axis = 1), None]
	vn[np.any(vn != 0, axis = 1), :] /= vlen
	return vn

def normalize_v3(arr):
	''' Normalize a numpy array of 3 component vectors shape=(n,3) '''
	lens = np.sqrt( arr[:,0]**2 + arr[:,1]**2 + arr[:,2]**2 )
	arr[:,0] /= lens
	arr[:,1] /= lens
	arr[:,2] /= lens
	return arr

# Y = Categorical Dependent variable
# X = Neuroimage
# covars = covariates
# scale = minmaxscaling
# X_output = output the (scaled) neuroimage residuals
#def chi_sqr_test(Y, X, covars = None, scale = True, X_output = False):
#	from sklearn.feature_selection import chi2
#	from scipy.stats import norm
#	from sklearn import preprocessing

#	if not all(np.equal(item, int(item)) for item in Y):
#		print "Y must contain interger categorical variables"
#		quit()
#	if covars is not None:
#		X = resid_covars(np.column_stack([np.ones(len(covars)),covars]), X)
#	else:
#		if len(Y) == X.shape[1]:
#			X = X.T
#	if scale:
#		min_max_scaler = preprocessing.MinMaxScaler(feature_range=(0,1))
#		X = min_max_scaler.fit_transform(X)
#	Chi, P = chi2(X, Y)
#	Z = norm.ppf(1-P)
#	if X_output:
#		return Chi, Z, P, X
#	else:
#		return Chi, Z, P

# input functions
def convert_mni_object(obj_file):
	# adapted from Jon Pipitone's script https://gist.github.com/pipitone/8687804
	obj = open(obj_file)
	_, _, _, _, _, _, numpoints = obj.readline().strip().split()
	numpoints = int(numpoints)
	vertices=[]
	normals=[]
	triangles=[]

	for i in range(numpoints):
		x, y, z = list(map(float,obj.readline().strip().split())) 
		vertices.append((x, y, z))
	assert obj.readline().strip() == ""
	# numpoints normals as (x,y,z)
	for i in range(numpoints):
		normals.append(tuple(map(float,obj.readline().strip().split())))

	assert obj.readline().strip() == ""
	nt=int(obj.readline().strip().split()[0]) # number of triangles
	_, _, _, _, _ = obj.readline().strip().split()
	assert obj.readline().strip() == ""
	# rest of the file is a list of numbers
	points = list(map(int, "".join(obj.readlines()).strip().split()))
	points = points[nt:]	# ignore these.. (whatever they are)
	for i in range(nt): 
		triangles.append((points.pop(0), points.pop(0), points.pop(0)))
	return np.array(vertices), np.array(triangles)

def convert_fs(fs_surface):
	v, f = nib.freesurfer.read_geometry(fs_surface)
	return v, f

def convert_gifti(gifti_surface):
	img = nib.load(gifti_surface)
	v, f = img.darrays[0].data, img.darrays[1].data
	return v, f

def convert_ply(name_ply):
	element = []
	size = []
	vertex_info = []
	vertex_dtype = []
	face_dtype = []
	face_info = []
	vertex_property = 0
	face_property = 0
	ply_ascii = False

	obj = open(name_ply)
	reader = obj.readline().strip().split()
	firstword = reader[0]

	# READ HEADER
	while firstword != 'end_header':
		reader = obj.readline().strip().split()
		firstword = reader[0]
		if firstword == 'format':
			ply_format = reader[1]
			if ply_format == 'binary_little_endian':
				ply_format = '<'
			elif ply_format == 'binary_big_endian':
				ply_format = '>'
			else:
				ply_ascii = True
		if firstword == 'element':
			element.append((reader[1]))
			size.append((reader[2]))
			if reader[1] == 'vertex':
				vertex_property = 1
			else:
				vertex_property = 0
			if reader[1] == 'face':
				face_property = 1
			else:
				face_property = 0
		if reader[0] == 'property':
			if vertex_property == 1:
				vertex_dtype.append((reader[1]))
				vertex_info.append((reader[2]))
			elif face_property == 1:
				face_dtype.append((reader[2]))
				face_dtype.append((reader[3]))
				face_info.append((reader[4]))
			else:
				print("Unknown property")

	# READ ELEMENTS
	for e in range(len(element)):
		# VERTEX DATA
		if element[e] == 'vertex':
			v = np.zeros((int(size[e]), 3), dtype=np.float32)
			c = np.zeros((int(size[e]), 3), dtype=np.uint8)
			if ply_ascii:
				for i in range(int(size[e])):
					reader = obj.readline().strip().split()
					v[i, 0] = np.array(reader[0]).astype(np.float)
					v[i, 1] = np.array(reader[1]).astype(np.float)
					v[i, 2] = np.array(reader[2]).astype(np.float)
					if len(vertex_info) == 6:
						c[i, 0] = np.array(reader[3]).astype(np.uint8)
						c[i, 1] = np.array(reader[4]).astype(np.uint8)
						c[i, 2] = np.array(reader[5]).astype(np.uint8)
			else:
				struct_fmt = ply_format
				for i in range(len(vertex_dtype)):
					if vertex_dtype[i] == 'float':
						struct_fmt += 'f'
					if vertex_dtype[i] == 'uchar':
						struct_fmt += 'B'
					if vertex_dtype[i] == 'int':
						struct_fmt += 'i'
				struct_len = struct.calcsize(struct_fmt)
				struct_unpack = struct.Struct(struct_fmt).unpack_from
				vcounter = 0
				while vcounter != int(size[e]):
					if len(vertex_dtype) > 3:
						s = struct_unpack(obj.read(struct_len))
						v[vcounter] = s[:3]
						c[vcounter] = s[3:]
						vcounter += 1
					else:
						s = struct_unpack(obj.read(struct_len))
						v[vcounter] = s[:3]
						vcounter += 1
		# FACE DATA
		if element[e] == 'face':
			if ply_ascii:
				reader = obj.readline().strip().split()
				numf = int(reader[0])
				f = np.zeros((int(size[e]), numf), dtype=np.int32)
				f[0] = reader[1:]
				fcounter = 1
				while fcounter != int(size[e]):
					reader = obj.readline().strip().split()
					f[fcounter] = reader[1:]
					fcounter += 1
			else:
				if face_dtype[0] == 'uchar':
					fcounter = 0
					while fcounter != int(size[e]):
						struct_unpack = struct.Struct(ply_format + 'B').unpack_from
						numf = struct_unpack(obj.read(1))[0]
						# creates empty face array if it doesn't exists
						try:
							f
						except NameError:
							f = np.zeros((int(size[e]), numf), dtype=np.int32)
						struct_fmt = ply_format
						for i in range(int(numf)):
							struct_fmt += 'i'
						struct_len = struct.calcsize(struct_fmt)
						struct_unpack = struct.Struct(struct_fmt).unpack_from
						s = struct_unpack(obj.read(struct_len))
						f[fcounter] = s
						fcounter += 1
	return (v, f, c)

def convert_fslabel(name_fslabel):
	obj = open(name_fslabel)
	reader = obj.readline().strip().split()
	reader = np.array(obj.readline().strip().split())
	if reader.ndim == 1:
		num_vertex = reader[0].astype(np.int)
	else:
		print('Error reading header')
	v_id = np.zeros((num_vertex)).astype(np.int)
	v_ras = np.zeros((num_vertex,3)).astype(np.float)
	v_value = np.zeros((num_vertex)).astype(np.float)
	for i in range(num_vertex):
		reader = obj.readline().strip().split()
		v_id[i] = np.array(reader[0]).astype(np.int)
		v_ras[i] = np.array(reader[1:4]).astype(np.float)
		v_value[i] = np.array(reader[4]).astype(np.float)
	return (v_id, v_ras, v_value)

#output functions

def save_waveform(v,f, outname):
	if not outname.endswith('obj'):
		outname += '.obj'
	outname=check_outname(outname)
	with open(outname, "a") as o:
		for i in range(len(v)):
			o.write("v %1.6f %1.6f %1.6f\n" % (v[i,0],v[i,1], v[i,2]) )
		for j in range(len(f)):
			o.write("f %d %d %d\n" % (f[j,0],f[j,1], f[j,2]) )
		o.close()

def save_stl(v,f, outname):
	if not outname.endswith('stl'):
		outname += '.stl'
	outname=check_outname(outname)
	v = np.array(v, dtype=np.float32, order = "C")
	f = np.array(f, dtype=np.int32, order = "C")
	tris = v[f]
	n = np.cross( tris[::,1 ] - tris[::,0]  , tris[::,2 ] - tris[::,0] )
	n = normalize_v3(n)
	with open(outname, "a") as o:
		o.write("solid surface\n")
		for i in range(tris.shape[0]):
			o.write("facet normal %1.6f %1.6f %1.6f\n"% (n[i,0],n[i,0],n[i,0]))
			o.write("outer loop\n")
			o.write("vertex %1.6f %1.6f %1.6f\n" % (tris[i,0,0],tris[i,0,1],tris[i,0,2]))
			o.write("vertex %1.6f %1.6f %1.6f\n" % (tris[i,1,0],tris[i,1,1],tris[i,1,2]))
			o.write("vertex %1.6f %1.6f %1.6f\n" % (tris[i,2,0],tris[i,2,1],tris[i,2,2]))
			o.write("endloop\n")
			o.write("endfacet\n")
		o.write("endfacet\n")
		o.close()


def save_fs(v,f, outname):
	if not outname.endswith('srf'):
		outname += '.srf'
	outname=check_outname(outname)
	nib.freesurfer.io.write_geometry(outname, v, f)


def save_ply(v, f, outname, color_array=None, output_binary=True):
	# check file extension
	if not outname.endswith('ply'):
		if output_binary:
			outname += '.ply'
		else:
			outname += '.ascii.ply'
	outname=check_outname(outname)

	# write header 
	header = ("ply\n")
	if output_binary:
		header += ("format binary_%s_endian 1.0\n" % (sys.byteorder))
		if sys.byteorder == 'little':
			output_fmt = '<'
		else:
			output_fmt = '>'
	else:
		header += ("format ascii 1.0\n")
	header += ("comment made with TFCE_mediation\n")
	header += ("element vertex %d\n" % len(v))
	header += ("property float x\n")
	header += ("property float y\n")
	header += ("property float z\n")
	if color_array is not None:
		header += ("property uchar red\n")
		header += ("property uchar green\n")
		header += ("property uchar blue\n")
	header += ("element face %d\n" % len(f))
	header += ("property list uchar int vertex_index\n")
	header += ("end_header\n")

	# write to file
	with open(outname, "a") as o:
		o.write(header)
		for i in range(len(v)):
			if output_binary:
				if color_array is not None:
					o.write(
						struct.pack(output_fmt + 'fffBBB', v[i, 0], v[i, 1], v[i, 2], color_array[i, 0], color_array[i, 1], color_array[i, 2]))
				else:
					o.write(struct.pack(output_fmt + 'fff', v[i, 0], v[i, 1], v[i, 2]))
			else:
				if color_array is not None:
					o.write("%1.6f %1.6f %1.6f %d %d %d\n" % (v[i, 0], v[i, 1], v[i, 2], color_array[i, 0], color_array[i, 1], color_array[i, 2]))
				else:
					o.write("%1.6f %1.6f %1.6f\n" % (v[i, 0], v[i, 1], v[i, 2]))
		for j in range(len(f)):
			if output_binary:
				o.write(struct.pack('<Biii', 3, f[j, 0], f[j, 1], f[j, 2]))
			else:
				o.write("3 %d %d %d\n" % (f[j, 0], f[j, 1], f[j, 2]))


#vertex paint functions
def convert_redtoyellow(threshold,img_data, baseColour=[227,218,201], save_colorbar = True):
	color_array = np.zeros((img_data.shape[0],3))
	color_cutoffs = np.linspace(threshold[0],threshold[1],256)
	colored_img_data = np.zeros_like(img_data)
	cV=0
	for k in img_data:
		colored_img_data[cV] = np.searchsorted(color_cutoffs, k, side="left")
		cV+=1
	color_array[:,0]=255
	color_array[:,1]=np.copy(colored_img_data)
	color_array[img_data<threshold[0]] = baseColour
	color_array[img_data>threshold[1]] = [255,255,0]

	cmap_name = 'red_yellow'
	cmap_array = np.array(( (np.ones(256)*255), np.linspace(0,255,256), np.zeros(256))).T
	rl_cmap = colors.ListedColormap(cmap_array/255)
	if save_colorbar:
		write_colorbar(threshold, rl_cmap, cmap_name, 'png')
		plt.clf()
	return color_array

def convert_bluetolightblue(threshold, img_data, baseColour=[227,218,201], save_colorbar = True):
	color_array = np.zeros((img_data.shape[0],3))
	color_cutoffs = np.linspace(threshold[0],threshold[1],256)
	colored_img_data = np.zeros_like(img_data)
	cV=0
	for k in img_data:
		colored_img_data[cV] = np.searchsorted(color_cutoffs, k, side="left")
		cV+=1
	color_array[:,1]=np.copy(colored_img_data)
	color_array[:,2]=255
	color_array[img_data<threshold[0]] = baseColour
	color_array[img_data>threshold[1]] = [0,255,255]

	cmap_name = 'blue_lightblue'
	cmap_array = np.array(( np.zeros(256), np.linspace(0,255,256), (np.ones(256)*255))).T
	blb_cmap = colors.ListedColormap(cmap_array/255)
	if save_colorbar:
		write_colorbar(threshold, blb_cmap, cmap_name, 'png')
		plt.clf()
	return color_array

def convert_mpl_colormaps(threshold,img_data, cmapName, baseColour=[227,218,201], save_colorbar = True):
	cmapFunc = plt.get_cmap(str(cmapName))
	color_array = np.zeros((img_data.shape[0],3))
	color_cutoffs = np.linspace(threshold[0],threshold[1],256)
	cV=0
	for k in img_data:
		temp_ = np.array(cmapFunc(np.searchsorted(color_cutoffs, k, side="left")))*255
		color_array[cV,:] = ((np.around(temp_[0]), np.around(temp_[1]), np.around(temp_[2])))
		cV+=1
	color_array[img_data<threshold[0]] = baseColour
	temp_ = np.array(cmapFunc(np.searchsorted(color_cutoffs, color_cutoffs[255], side="left")))*255 # safer
	color_array[img_data>=threshold[1]] = ((int(temp_[0]), int(temp_[1]), int(temp_[2])))
	if save_colorbar:
		write_colorbar(threshold, cmapFunc, cmapName, 'png')
		plt.clf()
	return color_array

def convert_fsannot(annot_name):
	labels, ctab, names  = nib.freesurfer.read_annot(annot_name)
	labels[labels==-1] = 0 # why is this necessary?????
	color_array = ctab[labels]
	color_array = color_array[:,:3]
	write_annot_legend(ctab, names, annot_name)
	return color_array

#write legends
def write_annot_legend(ctab, names, annot_name, outtype = 'png'):
	all_patches = []
	for i in range(len(names)):
		all_patches.append(mpatches.Patch(color=(ctab[i][:3]/256), label=names[i]))
	plt.figure()
	plt.legend(handles=[all_patches[l] for l in range(len(names))], loc=2)
	plt.axis('off')
	plt.savefig("%s_legend.%s" % (os.path.basename(annot_name), outtype),bbox_inches='tight')

def write_colorbar(threshold, input_cmap, name_cmap, outtype = 'png'):
	a = np.array([[threshold[0],threshold[1]]])
	plt.figure()
	img = plt.imshow(a, cmap=input_cmap)
	plt.gca().set_visible(False)
	cax = plt.axes([0.1, 0.1, 0.03, 0.8])
	plt.colorbar(orientation="vertical", cax=cax)
	plt.savefig("%s_colorbar.%s" % (os.path.basename(name_cmap), outtype),bbox_inches='tight')
	plt.clf()


# Converts a voxel image to a surface including outputs voxel values to paint vertex surface.
#
# Input:
# 3D array of a voxel image
#
# Output:
# v = vertices
# f = faces
# values = transformed voxels values to vertex space
# Optional variables:
# affine = affine [4x4] to convert vertices values to native space
# threshold = threshold for output of voxels
# data_mask = use a mask to create a surface backbone
def convert_voxel(img_data, affine = None, threshold = None, data_mask = None, absthreshold = None):
	try:
		from skimage import measure
	except:
		print("Error skimage is required")
		quit()

	if threshold is not None:
		print("Zeroing data less than threshold = %1.2f" % threshold)
		img_data[img_data<threshold] = 0
	if absthreshold is not None:
		print("Zeroing absolute values less than threshold = %1.2f" % absthreshold)
		img_data[np.abs(img_data)<absthreshold] = 0
	if data_mask is not None:
		print("Including mask")
		data_mask *= .1
		data_mask[img_data!=0] = img_data[img_data!=0]
		del img_data
		img_data = np.copy(data_mask)
	try:
		v, f, _, values = measure.marching_cubes_lewiner(img_data)
		if affine is not None:
			print("Applying affine transformation")
			v = nib.affines.apply_affine(affine,v)
	except:
		print("No voxels above threshold")
		v = f = values = []
	return v, f, values


# Applies laplacian smoothing with option to smooth single volume
#
# Herrmann, Leonard R. (1976), "Laplacian-isoparametric grid generation scheme", Journal of the Engineering Mechanics Division, 102 (5): 749–756.
#
# Input:
# v = vertices array
# f = face array
#
# Optional:
# scalar = scalar values
#
# Output:
# lapace_v = smoothed vertices array
# f = face array (unchanged)
# values = smoothed scalar array
def basic_laplacian_smoothing(v, f, adjacency = None, scalar = None):

	n = v.shape[0]
	laplace_v = np.empty((n,3))

	if adjacency is None:
		adjacency = create_adjac_vertex(v,f)
	if scalar is not None:
		values = np.empty((n))

	for i in range(n):
		neighbors = list(adjacency[i])
		if len(neighbors) > 0:
			laplace_v[i] = np.mean([v[j] for j in neighbors], axis = 0)
			if scalar is not None:
				values[i] = np.mean([scalar[j] for j in neighbors])
	if scalar is not None:
		return (laplace_v, f, values)
	else:
		return (laplace_v, f)

# Applies Laplacian or Taubin smoothing with option to smooth single volume
#
# Herrmann, Leonard R. (1976), "Laplacian-isoparametric grid generation scheme", Journal of the Engineering Mechanics Division, 102 (5): 749–756.
# Taubin, Gabriel. "A signal processing approach to fair surface design." Proceedings of the 22nd annual conference on Computer graphics and interactive techniques. ACM, 1995.
#
# Input:
# v = vertices array
# f = face array
# adjacency = adjacency set (probably best to use the mesh)
#
# Optional:
# scalar = scalar values
# lambda_w = postive factor
# mu_w = negative factor (note, mu_w = 0 is laplacian smoothing)
# mode = taubin or laplacian
#
# Output:
# v_taubin = smoothed vertices array
# f = face array (unchanged)
# values = smoothed scalar array
def surface_smooth(v, f, adjacency, iter_num = 0, scalar = None, lambda_w = 1.0, mode = 'laplacian', v_weighted = True):

	k = 0.1
	mu_w = -lambda_w/(1-k*lambda_w)
	n = v.shape[0]
	v_smooth = np.empty((n,3))

	if scalar is not None:
		values = np.empty((n))

	def v_new(v, vneighbors, v_factor, sneighbors = None):
		if len(vneighbors) > 0:
			weights = np.power(np.linalg.norm((vneighbors - v), axis = 1)[:,None], -1)
			vectors = weights * vneighbors
			w_vertex = v + (v_factor * ((np.sum(vectors, axis = 0)/np.sum(weights)) - v))
			if sneighbors is not None:
				w_scalar = np.mean(np.sum(weights * sneighbors,axis = 0) / np.sum(weights))
				return w_vertex, w_scalar
			return w_vertex

	def v_new_unweighted(v, vneighbors, v_factor = None, sneighbors = None):
		if sneighbors is not None:
			return np.mean(vneighbors, axis = 0), np.mean(sneighbors)
		else:
			return np.mean(vneighbors, axis = 0)

	if v_weighted:
		calc_Vnew = v_new
	else:
		calc_Vnew = v_new_unweighted


	for i in range(n):
		neighbors = list(adjacency[i])
		if len(neighbors) > 0:

			if iter_num % 2 == 0:
				if i == 1:
					print("Smoothing iteration (positive factor): %d" % (iter_num+1))
				if scalar is not None:
					v_smooth[i], values[i] = calc_Vnew(v[i], v[neighbors], lambda_w, scalar[neighbors])
				else:
					v_smooth[i] = calc_Vnew(v[i], v[neighbors], lambda_w)
			else:
				if mode == 'taubin':
					if i == 1:
						print("Smoothing iteration (negative factor): %d" % (iter_num+1))

					if scalar is not None:
						v_smooth[i], values[i] = calc_Vnew(v[i], v[neighbors], mu_w, scalar[neighbors])
					else:
						v_smooth[i] = calc_Vnew(v[i], v[neighbors], mu_w)


				elif mode == 'laplacian':
					if i == 1:
						print("Smoothing iteration (positive factor): %d" % (iter_num+1))

					if scalar is not None:
						v_smooth[i], values[i] = calc_Vnew(v[i], v[neighbors], lambda_w, scalar[neighbors])
					else:
						v_smooth[i] = calc_Vnew(v[i], v[neighbors], lambda_w)

				else:
					print("Error: smoothing type not understood")

	if scalar is not None:
		return (v_smooth, f, values)
	else:
		return (v_smooth, f)

# Applies Laplacian or Taubin smoothing with option to smooth single volume
#
# Herrmann, Leonard R. (1976), "Laplacian-isoparametric grid generation scheme", Journal of the Engineering Mechanics Division, 102 (5): 749–756.
# Taubin, Gabriel. "A signal processing approach to fair surface design." Proceedings of the 22nd annual conference on Computer graphics and interactive techniques. ACM, 1995.
#
# Input:
# v = vertices array
# f = face array
# adjacency = adjacency set (probably best to use the mesh)
#
# Optional:
# scalar = scalar values
# lambda_w = postive factor
# mode = taubin or laplacian
#
# Output:
# v_taubin = smoothed vertices array
# f = face array (unchanged)
# values = smoothed scalar array
def vectorized_surface_smooth(v, f, adjacency, number_of_iter = 5, scalar = None, lambda_w = 0.5, mode = 'laplacian', weighted = True):

	k = 0.1
	mu_w = -lambda_w/(1-k*lambda_w)

	lengths = np.array([len(a) for a in adjacency])
	maxlen = max(lengths)
	padded = [list(a) + [-1] * (maxlen - len(a)) for a in adjacency]
	adj = np.array(padded)
	w = np.ones(adj.shape, dtype=float)
	w[adj<0] = 0.
	val = (adj>=0).sum(-1).reshape(-1, 1)
	w /= val
	w = w.reshape(adj.shape[0], adj.shape[1],1)

	vorig = np.zeros_like(v)
	vorig[:] = v
	if scalar is not None:
		scalar[np.isnan(scalar)] = 0
		sorig = np.zeros_like(scalar)
		sorig[:] = scalar

	for iter_num in range(number_of_iter):
		if weighted:
			vadj = v[adj]
			vadj = np.swapaxes(v[adj],1,2)
			weights = np.zeros((v.shape[0], maxlen))
			for col in range(maxlen):
				weights[:,col] = np.power(np.linalg.norm(vadj[:,:,col] - v, axis=1),-1)
			weights[adj==-1] = 0
			vectors = np.einsum('abc,adc->acd', weights[:,None], vadj)

			if scalar is not None:
				scalar[np.isnan(scalar)] = 0

				sadj = scalar[adj]
				sadj[adj==-1] = 0
				if lambda_w < 1:
					scalar = (scalar*(1-lambda_w)) + lambda_w*(np.sum(np.multiply(weights, sadj),axis=1) / np.sum(weights, axis = 1))
				else:
					scalar = np.sum(np.multiply(weights, sadj),axis=1) / np.sum(weights, axis = 1)
				scalar[np.isnan(scalar)] = sorig[np.isnan(scalar)] # hacky scalar nan fix
			if iter_num % 2 == 0:
				v += lambda_w*(np.divide(np.sum(vectors, axis = 1), np.sum(weights[:,None], axis = 2)) - v)
			elif mode == 'taubin':
				v += mu_w*(np.divide(np.sum(vectors, axis = 1), np.sum(weights[:,None], axis = 2)) - v)
			elif mode == 'laplacian':
				v += lambda_w*(np.divide(np.sum(vectors, axis = 1), np.sum(weights[:,None], axis = 2)) - v)
			else:
				print("Error: mode %s not understood" % mode)
				quit()
			v[np.isnan(v)] = vorig[np.isnan(v)] # hacky vertex nan fix
		else:
			if scalar is not None:
				sadj = scalar[adj]
				sadj[adj==-1] = 0

				if lambda_w < 1:
					scalar = (scalar*(1-lambda_w)) + (lambda_w*np.divide(np.sum(sadj, axis = 1),lengths))
				else:
					scalar = np.divide(np.sum(sadj, axis = 1),lengths)
			if iter_num % 2 == 0:
				v += np.array(lambda_w*np.swapaxes(w,0,1)*(np.swapaxes(v[adj], 0, 1)-v)).sum(0)
			elif mode == 'taubin':
				v += np.array(mu_w*np.swapaxes(w,0,1)*(np.swapaxes(v[adj], 0, 1)-v)).sum(0)
			elif mode == 'laplacian':
				v += np.array(lambda_w*np.swapaxes(w,0,1)*(np.swapaxes(v[adj], 0, 1)-v)).sum(0)
			else:
				print("Error: mode %s not understood" % mode)
				quit()

	if scalar is not None:
		return (v, f, scalar)
	else:
		return (v, f)

# Applies regression using a voxel/vertex wise regressor
#
# Input
#
# y = masked image data (V x Subjects)
# image_x = image regressor
# pred_x = predictors
# covars = covariates
#
# Output
# arr = t-value image, image_covariate image
def image_regression(y, image_x, pred_x, covars = None, normalize = False, verbose = True):
	start_time = time()
	nv = y.shape[0]
	n = y.shape[1]
	if np.all(covars != None):
		regressors = np.column_stack((pred_x, covars))
	else:
		regressors = pred_x
	regressors = np.column_stack([np.ones(len(regressors)),regressors])
	arr = np.zeros((nv,len(regressors.T)+1))

	if normalize:
		image_x = zscaler(image_x, axis=0, w_mean=True, w_std=True)

	for i in range(nv):
		if i % 5000 == 0:
			print(i)
		if (image_x[i,:].std() < 0.01) or (np.any(np.isnan(image_x[i,:]))):
			arr[i,:] = 0
		else:
			temp_data = image_x[i,:]
			temp_y =  y[i,:]
			X = np.column_stack((regressors, temp_data))
			k = len(X.T)
			invXX = np.linalg.inv(np.dot(X.T, X))
			a = cy_lin_lstsqr_mat(X, temp_y)
			sigma2 = np.sum((temp_y - np.dot(X,a))**2,axis=0) / (n - k)
			se = np.sqrt(np.diag(sigma2 * invXX))
			arr[i] = a / se
	print(("Finished. Image-wise independent variable regression took %.1f seconds" % (time() - start_time)))
	return np.array(arr[:,:len(pred_x.T)+1], dtype=np.float32), np.array(np.squeeze(arr[:,-1:]), dtype=np.float32)

def image_reg_VIF(y, regressors):
	X = np.column_stack([np.ones(len(regressors)),regressors])
	a = cy_lin_lstsqr_mat(X, y)
	resids = y - np.dot(X,a)
	RSS = np.sum(resids**2,axis=0)
	TSS = np.sum((y - np.mean(y, axis =0))**2, axis = 0)
	R2 = 1 - (RSS/TSS)
	VIF = 1/(1-R2)
	VIF[np.isnan(VIF)] = 0
	return VIF



