import numpy as np
import scipy.integrate
import scipy.interpolate as interp

import input_parameters as IN

""""""""""""""""""""""""""""""""""""""""""""""""
"                                              "
"              MORPHOLOGY CLASSES              "
"  Contains classes that shape the simulated   "
"    galaxies, or otherwise integrates the     "
"      contributions by individual yields      "
"                                              "
" LIST OF CLASSES:                             "
"	__ 		Auxiliary                          "
"	__ 		Stellar_Lifetimes                  "
"	__		Infall                             "
"	__		Initial_Mass_Function              "
"	__		Star_Formation_Rate                "
"                                              "
""""""""""""""""""""""""""""""""""""""""""""""""

class Auxiliary:
	def varname(self, var, dir=locals()):
  		return [ key for key, val in dir.items() if id( val) == id( var)][0]
  
	def is_monotonic(self, arr):
		print ("for ", varname(arr)) 
		if all(arr[i] <= arr[i + 1] for i in range(len(arr) - 1)): 
			return "monotone increasing" 
		elif all(arr[i] >= arr[i + 1] for i in range(len(arr) - 1)):
			return "monotone decreasing"
		return "not monotonic array"
	
	def find_nearest(self, array, value):
		array = np.asarray(array)
		idx = (np.abs(array - value)).argmin()
		return idx

	def age_from_z(self, zf, h = 0.7, OmegaLambda0 = 0.7, Omegam0 = 0.3, Omegar0 = 1e-4, lookback_time = False):
		'''
		Finds the age (or lookback time) given a redshift (or scale factor).
		Assumes flat LCDM. Std cosmology, zero curvature. z0 = 0, a0 = 1.
		Omegam0 = 0.28 # 0.24 DM + 0.04 baryonic
		
		INPUT:	
		(aem = Float. Scale factor.)
		(OmegaLambda0 = 0.72, Omegam0 = 0.28)
		zf  = redshift
		
		OUTPUT
		lookback time.
		'''
		H0 = 100 * h * 3.24078e-20 * 3.15570e16 # [ km s^-1 Mpc^-1 * Mpc km^-1 * s Gyr^-1 ]
		#zf = np.reciprocal(np.float(aem))-1
		age = integrate.quad(lambda z: 1 / ( (z + 1) *np.sqrt(OmegaLambda0 + 
								Omegam0 * (z+1)**3 + Omegar0 * (z+1)**4) ), 
								zf, np.inf)[0] / H0 # Since BB [Gyr]
		if not lookback_time:
			return age
		else:
			age0 = integrate.quad(lambda z: 1 / ( (z + 1) *np.sqrt(OmegaLambda0 
								+ Omegam0 * (z+1)**3 + Omegar0 * (z+1)**4) ),
								 0, np.inf)[0] / H0 # present time [Gyr]
			return age0 - age


class Stellar_Lifetimes:
	'''
	Interpolation of Portinari+98 Table 14
	
	The first column of s_lifetimes_p98 identifies the stellar mass
	All the other columns indicate the respective lifetimes, 
	evaluated at different metallicities.
	
	'''
	def __init__(self):
		self.Z_names = ['Z0004', 'Z008', 'Z02', 'Z05']
		self.Z_binned = [0.0004, 0.008, 0.02, 0.05]
		self.Z_bins = [0.001789, 0.012649, 0.031623] # log-avg'd Z_binned
		self.s_mass = IN.s_lifetimes_p98['M']
	
	def interp_tau(self, idx):
		tau = IN.s_lifetimes_p98[self.Z_names[idx]] / 1e9
		return interp.interp1d(self.s_mass, tau)
	def stellar_lifetimes(self):
		return [self.interp_tau(ids) for ids in range(4)]
		
	def interp_M(self, idx):
		tau = IN.s_lifetimes_p98[self.Z_names[idx]] / 1e9
		return interp.interp1d(tau, self.s_mass)
	def stellar_masses(self):
		return [self.interp_M(idx) for idx in range(4)]
	
	def interp_stellar_lifetimes(self, metallicity):
		'''
		Picks the tau(M) interpolation at the appropriate metallicity
		'''
		Z_idx = np.digitize(metallicity, self.Z_bins)
		return self.stellar_lifetimes()[Z_idx]

	def interp_stellar_masses(self, metallicity):
		'''
		Picks the M(tau) interpolation at the appropriate metallicity
		'''
		Z_idx = np.digitize(metallicity, self.Z_bins)
		return self.stellar_masses()[Z_idx]


class Infall:
	'''
	CLASS
	Computes the infall as an exponential decay
	
	EXAMPLE:
		Infall_class = Infall(morphology)
		infall = Infall_class.inf()
	(infall will contain the infall rate at every time i in time)
	'''
	def __init__(self, morphology='spiral', option=IN.inf_option, time=None):
		self.morphology = IN.morphology
		self.time = time
		self.option = option
	
	def infall_func_simple(self):
		'''
		Analytical implicit function of an exponentially decaying infall.
		Only depends on time (in Gyr)
		'''
		return lambda t: np.exp(-t / IN.tau_inf[self.morphology])
		
	def two_infall(self):
		'''
		My version of Chiappini+01
		'''
		# After radial dependence upgrade
		return None
	
	def infall_func(self):
		'''
		Picks the infall function based on the option
		'''
		if not self.option:
			return self.infall_func_simple()
		elif self.option == 'two-infall':
			return self.two_infall()
		return None
	
	def aInf(self):
	    """
	    Computes the infall normalization constant
	    
	    USED IN:
	    	inf() and SFR()
	    """
	    return np.divide(IN.M_inf[self.morphology], 
	    				 scipy.integrate.quad(self.infall_func(),
	                     self.time[0], self.time[-1])[0])

	def inf(self):
	    '''
	    Returns the infall array
	    '''
	    return lambda t: self.aInf() * self.infall_func()(t)
	
	def inf_cumulative(self):
		'''
		Returns the total infall mass
		'''
		return np.sumcum(self.aInf())
		

class Initial_Mass_Function:
	'''
	CLASS
	Instantiates the IMF
	
	You may define custom IMFs, paying attention to the fact that:
	
	integrand = IMF * Mstar
	$\int_{Ml}^Mu integrand dx = 1$
	
	REQUIRES
		Mass (float) as input
	
	RETURNS
		normalized IMF by calling .IMF() onto the instantiated class
	
	Accepts a custom function 'func'
	Defaults options are 'Salpeter55', 'Kroupa03', [...]
	'''
	def __init__(self, Ml, Mu, option=IN.IMF_option, custom_IMF=IN.custom_IMF):
		self.Ml = Ml
		self.Mu = Mu
		self.option = option
		self.custom = custom_IMF
	
	def Salpeter55(self, plaw=1.35):
		return lambda Mstar: Mstar ** (-(1 + plaw))
		
	def Kroupa03(self):#, C = 0.31): #if m <= 0.5: lambda m: 0.58 * (m ** -0.30)/m
		'''
		Kroupa & Weidner (2003)
		'''
		if self.mass <= 1.0:
			plaw = 1.2
		else:
			plaw = 1.7
		return lambda Mstar: Mstar ** (-(1 + plaw))
		
	def IMF_select(self):
		if not self.custom:
			if self.option == 'Salpeter55':
					return self.Salpeter55()
			if self.option == 'Kroupa03':
					return self.Kroupa03()
		if self.custom:
			return self.custom
	
	def integrand(self, Mstar):
		return Mstar * self.IMF_select()(Mstar)
		
	def normalization(self):
		return np.reciprocal(scipy.integrate.quad(self.integrand, self.Ml, self.Mu)[0])
	
	def IMF(self):
		return lambda Mstar: self.IMF_select()(Mstar) * self.normalization()
		
	def IMF_test(self):
		'''
		Returns the normalized integrand integral. If the IMF works, it should return 1.
		'''
		return self.normalization() * scipy.integrate.quad(self.integrand, self.Ml, self.Mu)[0]
		
		
class Star_Formation_Rate:
	'''
	CLASS
	Instantiates the SFR
	
	Accepts a custom function 'func'
	Defaults options are 'SFRgal', 'CSFR', [...]
	'''
	def __init__(self, option=IN.SFR_option, custom=IN.custom_SFR, 
				 option_CSFR=IN.CSFR_option, morphology=IN.morphology):
		self.option = option
		self.custom = custom
		self.option_CSFR = option_CSFR
		self.morphology = morphology

	def SFRgal(self, morphology, k=IN.k_SFR):
		return lambda Mgas: IN.nu[morphology] * Mgas**(-k)	
	
	def CSFR(self):
		'''
		Cosmic Star Formation rate dictionary
			'md14'		Madau & Dickinson (2014)
			'hb06'		Hopkins & Beacom (2006)
			'f07'		Fardal (2007)
			'w08'		Wilken (2008)
			'sh03'		Springel & Hernquist (2003)
		'''
		CSFR = {'md14': (lambda z: (0.015 * np.power(1 + z, 2.7)) 
						 / (1 + np.power((1 + z) / 2.9, 5.6))), 
				'hb06': (lambda z: 0.7 * (0.017 + 0.13 * z) / (1 + (z / 3.3)**5.3)), 
				'f07': (lambda z: (0.0103 + 0.088 * z) / (1 + (z / 2.4)**2.8)), 
				'w08': (lambda z: (0.014 + 0.11 * z) / (1 + (z / 1.4)**2.2)), 
				'sh03': (lambda z: (0.15 * (14. / 15) * np.exp(0.6 * (z - 5.4)) 
						 / (14.0 / 15) - 0.6 + 0.6 * np.exp((14. / 15) * (z - 5.4))))}
		return CSFR.get(self.option_CSFR, "Invalid CSFR option")
		
	def SFR(self):
		if not self.custom:
			if self.option == 'SFRgal':
					return self.SFRgal(self.morphology)
			elif self.option == 'CSFR':
				if self.option_CSFR:
					return CSFR(self.option_CSFR)
				else:
					print('Please define the CSFR option "option_CSFR"')
		if self.custom:
			return self.custom
			
	def outflow(self, Mgas, morphology, SFR=SFRgal, wind_eff=IN.wind_efficiency, k=1):
		return wind_eff * SFR(Mgas, morphology)