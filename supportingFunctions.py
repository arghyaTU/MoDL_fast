"""
Created on July 5th, 20125

fastMRI compatible file contains some supporting functions used during training and testing.

@ Arghya
"""
import time
import numpy as np
import h5py as h5
import matplotlib.pyplot as plt
import os

#%%
def div0( a, b ):
    """ This function handles division by zero """
    c=np.divide(a, b, out=np.zeros_like(a), where=b!=0)
    return c

#%% This provide functionality similar to matlab's tic() and toc()
def TicTocGenerator():
    # Generator that returns time differences
    ti = 0           # initial time
    tf = time.time() # final time
    while True:
        ti = tf
        tf = time.time()
        yield tf-ti # returns the time difference

TicToc = TicTocGenerator() # create an instance of the TicTocGen generator

# This will be the main function through which we define both tic() and toc()
def toc(tempBool=True):
    # Prints the time difference yielded by generator instance TicToc
    tempTimeInterval = next(TicToc)
    if tempBool:
        print( "Elapsed time: %f seconds.\n" %tempTimeInterval )

def tic():
    # Records a time in TicToc, marks the beginning of a time interval
    toc(False)
#%%

def normalize01(img):
    """
    Normalize the image between o and 1
    """
    if len(img.shape)==3:
        nimg=len(img)
    else:
        nimg=1
        r,c=img.shape
        img=np.reshape(img,(nimg,r,c))
    img2=np.empty(img.shape,dtype=img.dtype)
    for i in range(nimg):
        img2[i]=div0(img[i]-img[i].min(),np.ptp(img[i]))
        #img2[i]=(img[i]-img[i].min())/(img[i].max()-img[i].min())
    return np.squeeze(img2).astype(img.dtype)

#%%
def np_crop(data, shape=(320,320)):

    w_from = (data.shape[-2] - shape[0]) // 2
    h_from = (data.shape[-1] - shape[1]) // 2
    w_to = w_from + shape[0]
    h_to = h_from + shape[1]
    return data[..., w_from:w_to, h_from:h_to]

#%%

def myPSNR(org,recon):
    """ This function calculates PSNR between the original and
    the reconstructed     images"""
    mse=np.sum(np.square( np.abs(org-recon)))/org.size
    psnr=20*np.log10(org.max()/(np.sqrt(mse)+1e-10 ))
    return psnr


#%% Here I am reading the dataset for training and testing from dataset.hdf5 file

def getData(trnTst='testing',num=100,sigma=0):
    #num: set this value between 0 to 163. There are total testing 164 slices in testing data
    print('Reading the data. Please wait...')
    filename='dataset5_s4.h5' #set the correct path here
    #filename='/Users/haggarwal/datasets/piData/dataset.hdf5'

    tic()
    with h5.File(filename) as f:
        if trnTst=='training':
            org=f['trnOrg'][:]
            csm=np.ones_like(org)
            csm = csm.reshape((416, 1, 256, 232))   # hard codematching dt5_s3.h5
            mask=f['trnMask'][:]
            print(f"org shape: {org.shape}")
            print(f"csm shape: {csm.shape}")
            print(f"mask shape: {mask.shape}")
            import matplotlib.pyplot as plt
            plt.imshow(np.abs(org[10]), cmap='gray')
            plt.title("Loaded Org Image (abs)")
            plt.savefig('temp/output.jpg', format='jpg', bbox_inches='tight')
            plt.show()
        else:
            org,csm,mask=f['tstOrg'][num],f['tstCsm'][num],f['tstMask'][num]
            na=np.newaxis
            org,csm,mask=org[na],csm[na],mask[na]
    toc()
    print('Successfully read the data from file!')
    print('Now doing undersampling....')
    tic()
    atb=generateUndersampled(org,csm,mask,sigma)
    toc()
    print('Successfully undersampled data!')
    if trnTst=='testing':
        atb=c2r(atb)
    return org,atb,csm,mask

#Here I am reading one single image from  demoImage.hdf5 for testing demo code
def getTestingData():
    print('Reading the data. Please wait...')
    filename='dataset5_s3.h5' #set the correct path here
    tic()
    with h5.File(filename,'r') as f:
            org=f['tstOrg'][:]
            csm=np.ones_like(org)
            csm = csm.reshape((68, 1, 256, 232))   # hard codematching dt5_s2.h5
            mask=f['trnMask'][:]
            print(f"org shape: {org.shape}")
            print(f"csm shape: {csm.shape}")
            print(f"mask shape: {mask.shape}")

    toc()
    print('Successfully read the data from file!')
    print('Now doing undersampling....')
    tic()
    atb=generateUndersampled(org,csm,mask,sigma=0)
    atb=c2r(atb)
    toc()
    print('Successfully undersampled data!')
    return org,atb,csm,mask


#%%
def piA(x,csm,mask,nrow,ncol,ncoil):
    """ This is a the A operator as defined in the paper"""
    ccImg=np.reshape(x,(nrow,ncol) )
    coilImages=np.tile(ccImg,[ncoil,1,1])*csm;
    kspace=np.fft.fft2(coilImages)/np.sqrt(nrow * ncol)
    if len(mask.shape)==2:
        mask=np.tile(mask,(ncoil,1,1))
    res=kspace[mask!=0]
    return res

def piAt(kspaceUnder,csm,mask,nrow,ncol,ncoil):
    """ This is a the A^T operator as defined in the paper"""
    temp=np.zeros((ncoil,nrow,ncol),dtype=np.complex64)
    if len(mask.shape)==2:
        mask=np.tile(mask,(ncoil,1,1))

    temp[mask!=0]=kspaceUnder
    img=np.fft.ifft2(temp)*np.sqrt(nrow*ncol)
    coilComb=np.sum(img*np.conj(csm),axis=0).astype(np.complex64)
    #coilComb=coilComb.ravel();
    return coilComb

def generateUndersampled(org,csm,mask,sigma=0.):
    nSlice,ncoil,nrow,ncol=csm.shape
    atb=np.empty(org.shape,dtype=np.complex64)
    for i in range(nSlice):
        A  = lambda z: piA(z,csm[i],mask[i],nrow,ncol,ncoil)
        At = lambda z: piAt(z,csm[i],mask[i],nrow,ncol,ncoil)

        sidx=np.where(mask[i].ravel()!=0)[0]
        nSIDX=len(sidx)
        noise=np.random.randn(nSIDX*ncoil,)+1j*np.random.randn(nSIDX*ncoil,)
        noise=noise*(sigma/np.sqrt(2.))
        y=A(org[i]) + noise
        atb[i]=At(y)
    return atb


#%%
def r2c(inp):
    """  input img: row x col x 2 in float32
    output image: row  x col in complex64
    """
    if inp.dtype=='float32':
        dtype=np.complex64
    else:
        dtype=np.complex128
    out=np.zeros( inp.shape[0:2],dtype=dtype)
    out=inp[...,0]+1j*inp[...,1]
    return out

def c2r(inp):
    """  input img: row x col in complex64
    output image: row  x col x2 in float32
    """
    if inp.dtype=='complex64':
        dtype=np.float32
    else:
        dtype=np.float64
    out=np.zeros( inp.shape+(2,),dtype=dtype)
    out[...,0]=inp.real
    out[...,1]=inp.imag
    return out

#%%
def getWeights(wtsDir,chkPointNum='last'):
    """
    Input:
        wtsDir: Full path of directory containing modelTst.meta
        nLay: no. of convolution+BN+ReLu blocks in the model
    output:
        wt: numpy dictionary containing the weights. The keys names ae full
        names of corersponding tensors in the model.
    """
    tf.reset_default_graph()
    if chkPointNum=='last':
        loadChkPoint=tf.train.latest_checkpoint(wtsDir)
    else:
        loadChkPoint=wtsDir+'/model'+chkPointNum
    config = tf.ConfigProto()
    config.gpu_options.allow_growth=True
    with tf.Session(config=config) as s1:
        saver = tf.train.import_meta_graph(wtsDir + '/modelTst.meta')
        saver.restore(s1, loadChkPoint)
        keys=[n.name+':0' for n in tf.get_default_graph().as_graph_def().node if "Variable" in n.op]
        var=tf.global_variables()

        wt={}
        for key in keys:
            va=[v for v in var if v.name==key][0]
            wt[key]=s1.run(va)

    tf.reset_default_graph()
    return wt

def assignWts(sess1,nLay,wts):
    """
    Input:
        sess1: it is the current session in which to restore weights
        nLay: no. of convolution+BN+ReLu blocks in the model
        wts: numpy dictionary containing the weights
    """

    var=tf.global_variables()
    #check lam and beta; these for for alternate strategy scalars

    #check lamda 1
    tfV=[v for v in var if 'lam1' in v.name and 'Adam' not in v.name]
    npV=[v for v in wts.keys() if 'lam1' in v]
    if len(tfV)!=0 and len(npV)!=0:
        sess1.run(tfV[0].assign(wts[npV[0]] ))
    #check lamda 2
    tfV=[v for v in var if 'lam2' in v.name and 'Adam' not in v.name]
    npV=[v for v in wts.keys() if 'lam2' in v]
    if len(tfV)!=0 and len(npV)!=0:  #in single channel there is no lam2 so length is zero
        sess1.run(tfV[0].assign(wts[npV[0]] ))

    # assign W,b,beta gamma ,mean,variance
    #for each layer at a time
    for i in np.arange(1,nLay+1):
        tfV=[v for v in var if 'conv'+str(i) +str('/') in v.name \
             or 'Layer'+str(i)+str('/') in v.name and 'Adam' not in v.name]
        npV=[v for v in wts.keys() if  ('Layer'+str(i))+str('/') in v or'conv'+str(i)+str('/') in v]
        tfv2=[v for v in tfV if 'W:0' in v.name]
        npv2=[v for v in npV if 'W:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
        tfv2=[v for v in tfV if 'b:0' in v.name]
        npv2=[v for v in npV if 'b:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
        tfv2=[v for v in tfV if 'beta:0' in v.name]
        npv2=[v for v in npV if 'beta:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
        tfv2=[v for v in tfV if 'gamma:0' in v.name]
        npv2=[v for v in npV if 'gamma:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
        tfv2=[v for v in tfV if 'moving_mean:0' in v.name]
        npv2=[v for v in npV if 'moving_mean:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
        tfv2=[v for v in tfV if 'moving_variance:0' in v.name]
        npv2=[v for v in npV if 'moving_variance:0' in v]
        if len(tfv2)!=0 and len(npv2)!=0:
            sess1.run(tfv2[0].assign(wts[npv2[0]]))
    return sess1


def gen_mask(shape, acceleration_factor):
    """
    Generates a 2D Gaussian undersampling mask by sampling points based on a 2D Gaussian distribution.

    Args:
        shape (tuple): The shape of the desired mask (e.g., (256, 256)).
        acceleration_factor (float): The desired acceleration factor.
                                     Higher values result in more undersampling.

    Returns:
        numpy.ndarray: A 2D boolean numpy array representing the mask,
                       where True indicates a sampled k-space point.
    """
    if len(shape) != 2:
        raise ValueError("Shape must be a 2D tuple (height, width).")

    rows, cols = shape
    mask = np.zeros(shape, dtype=bool)

    # Create a 2D Gaussian probability distribution
    x, y = np.meshgrid(np.linspace(-1, 1, cols), np.linspace(-1, 1, rows))
    d = np.sqrt(x*x + y*y)
    sigma, mu = 0.5, 0.0
    gaussian_2d = np.exp(-((d - mu)**2 / (2.0 * sigma**2)))
    gaussian_2d /= gaussian_2d.sum() # Normalize to sum to 1

    # Determine the number of points to sample
    # This is an approximation, the actual acceleration might vary slightly
    total_points = rows * cols
    num_sampled_points = int(total_points / acceleration_factor)

    # Ensure at least one point is sampled
    if num_sampled_points < 1:
        num_sampled_points = 1

    # Flatten the 2D Gaussian distribution and generate indices based on probabilities
    gaussian_flat = gaussian_2d.ravel()
    sampled_indices_flat = np.random.choice(total_points, size=num_sampled_points, replace=False, p=gaussian_flat)

    # Convert flattened indices back to 2D indices
    sampled_rows, sampled_cols = np.unravel_index(sampled_indices_flat, shape)

    # Set the sampled points in the mask to True
    mask[sampled_rows, sampled_cols] = True

    return mask
def generate_1d_gaussian_mask(M, N, R):
    """
    Generates a 1D vertical Gaussian undersampling mask.

    Args:
        M (int): The height of the k-space (number of vertical lines).
        N (int): The width of the k-space.
        R (float): The desired acceleration factor.

    Returns:
        np.ndarray: A 2D numpy array representing the undersampling mask.
        int: The actual number of lines sampled.
    """
    # 1. Calculate the number of vertical lines to sample
    num_sampled_lines = int(N / R)
    if num_sampled_lines == 0:
        num_sampled_lines = 1
    #print(f"Targeting {num_sampled_lines} lines out of {N} for R={R}.")

    # 2. Create a 1D Gaussian probability distribution
    # The center of the distribution will be at the center of k-space (M/2)
    center_k_space = N // 2
    # The standard deviation (sigma) controls the spread. A smaller sigma
    # means a more concentrated sampling at the center. A good starting
    # point is a fraction of the total lines.
    sigma = N / 8

    # Create an array of indices from 0 to M-1
    line_indices = np.arange(N)

    # Calculate the Gaussian probability for each line index
    probabilities = np.exp(-((line_indices - center_k_space)**2) / (2 * sigma**2))

    # Normalize the probabilities so they sum to 1
    probabilities /= np.sum(probabilities)

    # 3. Select lines to sample based on the Gaussian distribution
    # We use weighted random sampling *without replacement* to ensure we get
    # the exact number of unique lines we need.
    sampled_indices = np.random.choice(
        a=line_indices,
        size=num_sampled_lines,
        replace=False,
        p=probabilities
    )

    # 4. Create the 2D mask image
    mask = np.zeros((M, N), dtype=np.float32)
    for index in sampled_indices:
        mask[:, index] = 1  # Set the entire selected row to 1

    return mask, len(sampled_indices)

def plot_mask(mask, title):
    """
    Plots and saves the generated mask.
    """
    plt.figure(figsize=(6, 8))
    plt.imshow(mask, cmap='gray', aspect='auto')
    plt.title(title, fontsize=14)
    plt.xlabel("k-space (kx)")
    plt.ylabel("k-space (ky)")

    # Save the figure
    filename = "mask_1d_gaussian_vertical_R4.png"
    plt.savefig(filename)
    print(f"\nMask image saved as '{filename}'")

    plt.show()

def save_mask_as_npz(mask, filename):
    """
    Saves the generated mask as a .npz file.
    """
    np.savez_compressed(filename, mask=mask)
    print(f"Mask saved as '{filename}'")
