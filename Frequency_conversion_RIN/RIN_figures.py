import numpy as np
import matplotlib.pyplot as plt
import os 
from scipy.integrate import trapezoid
from numpy.typing import ArrayLike
from brokenaxes import brokenaxes

### Methods
def dB_to_linear(RIN_dB: ArrayLike):

    return 10**(RIN_dB/10)


def linear_to_dB(RIN_lin: ArrayLike):
    
    return 10*np.log10(RIN_lin)


def integrated_RIN(freqs: ArrayLike, RIN_dB: ArrayLike): #Input is dB/Hz output is linear

    RIN_lin = dB_to_linear(RIN_dB)

    int_RIN_lin = trapezoid(x=freqs,y=RIN_lin)

    return int_RIN_lin


def SHG_RIN_spec(RIN_pump: ArrayLike): #reduced RIN (Isserlis' theorem applied) without dirac delta function. Input and output RIN is in dB/Hz

    RIN_lin = dB_to_linear(RIN_pump)

    SHG_RIN_lin = 4*RIN_lin + 2* RIN_lin**2

    return linear_to_dB(SHG_RIN_lin)

def approx_SHG_RIN_spec(RIN_pump: ArrayLike): #Approximate SHG RIN. Input and output RIN is in dB/Hz

    RIN_lin = dB_to_linear(RIN_pump)

    SHG_RIN_lin = 4*RIN_lin

    return linear_to_dB(SHG_RIN_lin)


def SFG_RIN_spec(RIN_pump_1: ArrayLike, RIN_pump_2: ArrayLike): #reduced RIN (Isserlis' theorem applied) for completely uncorrelated pumps. Input and output RIN is in dB/Hz

    RIN_lin_1 = dB_to_linear(RIN_pump_1)
    RIN_lin_2 = dB_to_linear(RIN_pump_2)

    SFG_RIN_lin = RIN_lin_1 + RIN_lin_2 + RIN_lin_1*RIN_lin_2

    return linear_to_dB(SFG_RIN_lin)


def cascaded_RIN_spec(freqs: ArrayLike, RIN_pump: ArrayLike): #reduced RIN (Isserlis' theorem applied) without dirac delta function. Input and output RIN is in dB/Hz

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    cascaded_RIN_lin = RIN_lin*(9 + 18*RIN_int + 9*RIN_int**2) + 18*RIN_lin**2 + 6*RIN_lin**3

    return linear_to_dB(cascaded_RIN_lin)


def THG_RIN_spec(freqs: ArrayLike, RIN_pump: ArrayLike): #reduced RIN (Isserlis' theorem applied) without dirac delta function. Input and output RIN is in dB/Hz

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    cascaded_RIN_lin = RIN_lin*(9 + 18*RIN_int + 9*RIN_int**2) + 18*RIN_lin**2 + 6*RIN_lin**3

    return linear_to_dB(cascaded_RIN_lin)

def approx_THG_RIN_spec(RIN_pump: ArrayLike): #Approximate THG RIN. Input and output RIN is in dB/Hz
    
    RIN_THG = linear_to_dB(dB_to_linear(RIN_pump)*9)

    return RIN_THG


def THG_RIN_spec_var(RIN_pump: ArrayLike, RIN_int_dB: float): #reduced RIN (Isserlis' theorem applied) without dirac delta function. Input and output RIN is in dB/Hz

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = dB_to_linear(RIN_int_dB)

    # RIN_int = var # variance/1mW^2 such that we get the integrated RIN value 

    cascaded_RIN_lin = RIN_lin*(9 + 18*RIN_int + 9*RIN_int**2) + 18*RIN_lin**2 + 6*RIN_lin**3

    return linear_to_dB(cascaded_RIN_lin)


### Terms comparison

def RIN_squared(RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_sq = RIN_lin**2

    return linear_to_dB(RIN_sq)

    
def RIN_tripled(RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_tri = RIN_lin**3

    return linear_to_dB(RIN_tri)
    

def variance_offset(freqs: ArrayLike, RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    return linear_to_dB(RIN_int)

    
def variance_squared_offset(freqs: ArrayLike, RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    return linear_to_dB(RIN_int**2)


def RIN_variance(freqs: ArrayLike, RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    return linear_to_dB(RIN_lin*RIN_int)
    

def RIN_variance_squared(freqs: ArrayLike, RIN_pump: ArrayLike):

    RIN_lin = dB_to_linear(RIN_pump)

    RIN_int = trapezoid(x=freqs,y=RIN_lin)

    return linear_to_dB(RIN_lin*RIN_int**2)



### Load data
data_path = r".\RIN data"

files = os.listdir(data_path)

for file in files:
    if '2095' in file:
        pump_path = data_path + '\\' + file 

    if 'SHG' in file:
        SHG_path = data_path + '\\' + file 
        
    if 'THG' in file:
        THG_path = data_path + '\\' + file

    if 'SFG' in file:
        SFG_path = data_path + '\\' + file
    
    if '1081' in file:
        SFG_pump1_path = data_path + '\\' + file

    if '1970' in file:
        SFG_pump2_path = data_path + '\\' + file

pump_data = np.loadtxt(pump_path)

SHG_data = np.loadtxt(SHG_path)

THG_data = np.loadtxt(THG_path)

SFG_data = np.loadtxt(SFG_path)

SFG_pump1_data = np.loadtxt(SFG_pump1_path)

SFG_pump2_data = np.loadtxt(SFG_pump2_path)


x_lim_start = 1e3
x_lim_end = 1e7

pump_freqs = pump_data[:,0][( (pump_data[:,0]> x_lim_start ) & (pump_data[:,0]< x_lim_end))]
pump_RIN = pump_data[:,1][( (pump_data[:,0]> x_lim_start) & (pump_data[:,0]< x_lim_end))]

SHG_freqs = SHG_data[:,0][( (SHG_data[:,0]> x_lim_start) & (SHG_data[:,0]< x_lim_end))]
SHG_RIN = SHG_data[:,1][( (SHG_data[:,0]> x_lim_start) & (SHG_data[:,0]< x_lim_end))]

THG_freqs = THG_data[:,0][( (THG_data[:,0]> x_lim_start) & (THG_data[:,0]< x_lim_end))]
THG_RIN = THG_data[:,1][( (THG_data[:,0]> x_lim_start) & (THG_data[:,0]< x_lim_end))]

SFG_freqs = SFG_data[:,0][( (SFG_data[:,0]> x_lim_start) & (SFG_data[:,0]< x_lim_end))]
SFG_RIN = SFG_data[:,1][( (SFG_data[:,0]> x_lim_start) & (SFG_data[:,0]< x_lim_end))]

SFG_pump1_freqs = SFG_pump1_data[:,0][( (SFG_pump1_data[:,0]> x_lim_start) & (SFG_pump1_data[:,0]< x_lim_end))]
SFG_pump1_RIN = SFG_pump1_data[:,1][( (SFG_pump1_data[:,0]> x_lim_start) & (SFG_pump1_data[:,0]< x_lim_end))]

SFG_pump2_freqs = SFG_pump2_data[:,0][( (SFG_pump2_data[:,0]> x_lim_start) & (SFG_pump2_data[:,0]< x_lim_end))]
SFG_pump2_RIN = SFG_pump2_data[:,1][( (SFG_pump2_data[:,0]> x_lim_start) & (SFG_pump2_data[:,0]< x_lim_end))]


### Calculate theoretical values based on pump RIN

SHG_theory_RIN = SHG_RIN_spec(pump_RIN)
THG_theory_RIN = THG_RIN_spec(pump_freqs,pump_RIN)
SFG_theory_RIN = SFG_RIN_spec(SFG_pump1_RIN, SFG_pump2_RIN)


### Make RIN spectrum plot
fig, [axRIN,axP] = plt.subplots(nrows=2,ncols=1,figsize=(3.35,4.1),height_ratios=[5,2.]) #old figsize: figsize=(4.15,5.17)

marksize = 2
fontsize = 9
labelsize = 8

#THG
axRIN.plot(THG_freqs,THG_RIN, color='red', label='698 nm (THG)', linewidth=marksize)

axRIN.plot(pump_freqs,THG_theory_RIN, ':', color='red', label = '_nolegend_', linewidth=marksize)

axRIN.plot(SHG_freqs,SHG_RIN, color='darkorange', label='1047 nm (SHG)', linewidth=marksize)

axRIN.plot(pump_freqs,SHG_theory_RIN,':', color='darkorange',label='_nolegend_', linewidth=marksize)

axRIN.plot(pump_freqs,pump_RIN, color='brown', label='2094 nm', linewidth=marksize)

#SFG
axRIN.plot(SFG_freqs,SFG_RIN, color='blue', label='698 nm (SFG)', linewidth=marksize)

axRIN.plot(SFG_pump1_freqs,SFG_pump1_RIN, color='cornflowerblue', label='1082 nm', linewidth=marksize)
axRIN.plot(SFG_pump2_freqs,SFG_pump2_RIN, color='darkblue', label='1970 nm', linewidth=marksize)

axRIN.plot(SFG_freqs,SFG_theory_RIN, ':', color='blue', label='_nolegend_', linewidth=marksize)


axRIN.set_ylabel('RIN [dBc/Hz]', fontweight='bold', fontsize=fontsize)
axRIN.xaxis.set_tick_params(labelsize=labelsize)
axRIN.yaxis.set_tick_params(labelsize=labelsize)

axRIN.set_xscale('log')
axRIN.set_xlim([1e3,1e7])
axRIN.set_ylim([-174,-78])
axRIN.set_yticks(np.arange(-160,-70,20))
axRIN.legend(ncol=2,fontsize=labelsize,loc='lower center')
axRIN.grid(True,which='minor',alpha=0.15)
axRIN.grid(True,which='major',alpha=0.5)

fig.subplots_adjust(left=0.175, right=0.97, top=0.99, bottom=0.125, hspace = 0.15)
fig.tight_layout()


#Penalty plot
axP.plot(THG_freqs,THG_RIN-pump_RIN,color='red',label='THG', linewidth=marksize)
axP.plot(THG_freqs,THG_theory_RIN-pump_RIN, ':', color='red',label='_nolegend_', linewidth=marksize)

axP.plot(SHG_freqs,SHG_RIN-pump_RIN,color='darkorange',label='SHG', linewidth=marksize)
axP.plot(SHG_freqs,SHG_theory_RIN-pump_RIN,':',color='darkorange',label='_nolegend_', linewidth=marksize)

SFG_pump_sum_RIN = linear_to_dB(dB_to_linear(SFG_pump1_RIN) + dB_to_linear(SFG_pump2_RIN))

axP.plot(SFG_freqs,SFG_RIN-SFG_pump_sum_RIN,color='blue',label='SFG', linewidth=marksize)
axP.plot(SFG_freqs,SFG_theory_RIN-SFG_pump_sum_RIN, ':', color='blue',label='_nolegend_', linewidth=marksize)


axP.set_xlabel('Frequency [Hz]', fontweight='bold', fontsize=fontsize,labelpad=2.2)
axP.set_ylabel('RIN penalty [dB/Hz]',fontweight='bold', fontsize=fontsize,labelpad=7)
axP.xaxis.set_tick_params(labelsize=labelsize)
axP.yaxis.set_tick_params(labelsize=labelsize)

axP.grid()
axP.set_ylim([-5,20])
axP.set_xlim([1e3,1e7])
axP.set_yticks([0,6,9.5,14])


plt.show()


# plt.savefig(r".\RIN_spectrum_combined.svg")

# plt.savefig(r".\RIN_spectrum_combined.pdf")


### Generate data for integrated RIN plots

#Integrate experimental data
RIN_int_pump = linear_to_dB(integrated_RIN(pump_freqs,pump_RIN))
RIN_int_SHG_data = linear_to_dB(integrated_RIN(SHG_freqs,SHG_RIN))
RIN_int_SFG_data = linear_to_dB(integrated_RIN(SFG_freqs,SFG_RIN))
RIN_int_THG_data = linear_to_dB(integrated_RIN(pump_freqs,THG_RIN))

#Calculate values based on scaled pump data
num_values = 1000

avg_RIN_spec_pump_values = np.logspace(-1,8,num_values) #Multiplied to our actual measured pump noise spectrum

num_points = len(pump_freqs)

RIN_int_pump_calc = np.ones((num_values))
RIN_int_SHG_calc = np.ones((num_values))
RIN_int_SFG_calc = np.ones((num_values))
RIN_int_THG_calc = np.ones((num_values))

RIN_int_SHG_approx_calc = np.ones((num_values))
RIN_int_SFG_sum_p1_p_2 = np.ones((num_values))
RIN_int_THG_approx_calc = np.ones((num_values))

#Individual higher-order RIN terms
RIN_squared_int = np.ones((num_values))
RIN_tripled_int = np.ones((num_values))
variance_offset_int = np.ones((num_values))   
variance_squared_offset_int = np.ones((num_values))   
RIN_variance_int = np.ones((num_values))   
RIN_variance_squared_int = np.ones((num_values))   

for i,avg_RIN_pump_value in enumerate(avg_RIN_spec_pump_values):

    avg_RIN_spec_pump =  linear_to_dB(dB_to_linear(pump_RIN) * avg_RIN_pump_value)  #Multiply RIN input spectrum with values above in linear scale and insert that as x-scale when integrated 

    pump_int_RIN = integrated_RIN(pump_freqs,avg_RIN_spec_pump)
    SHG_theory_RIN = SHG_RIN_spec(avg_RIN_spec_pump) #from dB to dB
    THG_theory_RIN = THG_RIN_spec(pump_freqs,avg_RIN_spec_pump)
    SFG_theory_RIN = SFG_RIN_spec(avg_RIN_spec_pump,avg_RIN_spec_pump)

    SHG_approx_RIN = approx_SHG_RIN_spec(avg_RIN_spec_pump)
    SFG_sum_p1_p2_RIN = linear_to_dB( dB_to_linear(avg_RIN_spec_pump) + dB_to_linear(avg_RIN_spec_pump) )
    THG_approx_RIN = approx_THG_RIN_spec(avg_RIN_spec_pump)


    RIN_int_pump_calc[i] = linear_to_dB(pump_int_RIN) # sanity check
    RIN_int_SHG_calc[i] = linear_to_dB(integrated_RIN(pump_freqs,SHG_theory_RIN) + pump_int_RIN**2) #Adding the delta function, that gives an addition of int. RIN^2. 
    RIN_int_SFG_calc[i] = linear_to_dB(integrated_RIN(pump_freqs,SFG_theory_RIN)) #Integrated RIN: dB to linear
    RIN_int_THG_calc[i] = linear_to_dB(integrated_RIN(pump_freqs,THG_theory_RIN) + 9 * pump_int_RIN**2) #Adding the delta function, that gives an addition of int. 9 RIN^2) 

    RIN_int_SHG_approx_calc[i] = linear_to_dB(integrated_RIN(pump_freqs,SHG_approx_RIN))
    RIN_int_SFG_sum_p1_p_2[i] = linear_to_dB(integrated_RIN(pump_freqs,SFG_sum_p1_p2_RIN))
    RIN_int_THG_approx_calc[i] = linear_to_dB(integrated_RIN(pump_freqs,THG_approx_RIN))

    #Individual terms
    RIN_sq = RIN_squared(avg_RIN_spec_pump)
    RIN_tri = RIN_tripled(avg_RIN_spec_pump)

    var_off = variance_offset(pump_freqs, avg_RIN_spec_pump)
    var_sq_off = variance_squared_offset(pump_freqs, avg_RIN_spec_pump)

    RIN_var = RIN_variance(pump_freqs, avg_RIN_spec_pump)
    RIN_var_sq = RIN_variance_squared(pump_freqs, avg_RIN_spec_pump)

    RIN_squared_int[i] = linear_to_dB(integrated_RIN(pump_freqs,RIN_sq))
    RIN_tripled_int[i] = linear_to_dB(integrated_RIN(pump_freqs,RIN_tri))

    variance_offset_int[i] = var_off
    variance_squared_offset_int[i] = var_sq_off

    RIN_variance_int[i] = linear_to_dB(integrated_RIN(pump_freqs,RIN_var))
    RIN_variance_squared_int[i] =  linear_to_dB(integrated_RIN(pump_freqs,RIN_var_sq))



### Make scaled integrated RIN plot
RIN_int_pump_values = RIN_int_pump_calc

plt.figure(figsize=(3.35,2.5))

bax = brokenaxes(ylims=((-5e-7,1e-5),(5,17)),hspace=0.15,height_ratios=(1,0.15))

bax.plot(RIN_int_pump_values,RIN_int_SHG_calc-RIN_int_pump_values, label='SHG', color = 'darkorange',linewidth=marksize)
bax.plot(RIN_int_pump_values,RIN_int_SFG_calc-RIN_int_SFG_sum_p1_p_2, label='SFG', color = 'blue',linewidth=marksize)
bax.plot(RIN_int_pump_values,RIN_int_THG_calc-RIN_int_pump_values, label='THG', color = 'red', alpha = 0.8, linewidth=marksize)

bax.plot(RIN_int_pump_values,RIN_int_SHG_approx_calc-RIN_int_pump_values, ls='--', color = 'darkorange',  label=r'$4\,\mathrm{RIN}_1$', alpha = 0.8, linewidth=marksize)
bax.plot(RIN_int_pump_values,RIN_int_SFG_sum_p1_p_2-RIN_int_SFG_sum_p1_p_2, ls='--', color = 'blue', label = r'$\mathrm{RIN}_1 + \mathrm{RIN}_2$', alpha = 0.8, linewidth=marksize)
bax.plot(RIN_int_pump_values,RIN_int_THG_approx_calc-RIN_int_pump_values, ls='--', color = 'red', label=r'$9\,\mathrm{RIN}_1$', alpha = 0.8, linewidth=marksize)

bax.legend(ncol=2,loc='upper left',fontsize=labelsize)

bax.grid()
bax.set_xlim([-50,0])

bax.set_xlabel('Pump Integrated RIN [dBc]', fontweight='bold', fontsize=fontsize,labelpad=20)
bax.set_ylabel('Integrated RIN increase [dB]',fontweight='bold', fontsize=fontsize, labelpad=30)

for ax in bax.axs:
    ax.minorticks_on()
    ax.grid(True,which='minor',alpha=0.15)
    ax.grid(True,which='major',alpha=0.5)

    ax.axvline(x=RIN_int_pump,color='black',linestyle=':',linewidth=marksize-0.5, alpha=0.7)

bax.tick_params(axis='x',labelsize=labelsize)
bax.tick_params(axis='y',labelsize=labelsize)

bax.axs[0].tick_params(axis='x',which='both',bottom=False,top=False,labelbottom=False)
bax.axs[1].set_yticks([0,1e-5])
bax.axs[1].set_yticklabels(['0', '1e-5'])
bax.axs[0].set_yticks([6,8,10,12,14,16])
bax.axs[0].set_yticklabels(['6','8','10','12','14','16'])

#Make arrows
bax.axs[1].annotate('Integral value\nof 2094 nm\nRIN data', xy=(RIN_int_pump, 4e-6),xytext=(RIN_int_pump+6, 5e-6), arrowprops=dict(arrowstyle='->',color='k',lw=1),fontsize=labelsize)
bax.axs[0].annotate('', xy=(RIN_int_pump, 5.5), xytext=(RIN_int_pump+5.5, 5), arrowprops=dict(arrowstyle='->', color='k', lw=1), fontsize=labelsize)

fig = bax.fig
fig.canvas.draw()

# get the positions (Bbox) of all internal axes (in figure coords)
bboxes = [ax.get_position() for ax in bax.axs]

# compute union bbox (min x0,y0 and max x1,y1)
x0 = min(b.x0 for b in bboxes)
y0 = min(b.y0 for b in bboxes)
x1 = max(b.x1 for b in bboxes)
y1 = max(b.y1 for b in bboxes)

rect = plt.Rectangle((x0, y0),(x1 - x0),(y1 - y0),transform=fig.transFigure,fill=False,linewidth=0.8,edgecolor='black',zorder=10) # draw rectangle in figure coordinates
fig.patches.append(rect)

plt.show()

# plt.savefig(r".\Int_RIN_spectrum_approx_vs_higher_order.pdf",bbox_inches='tight')
# plt.savefig(r".\Int_RIN_spectrum_approx_vs_higher_order.svg",bbox_inches='tight')


### Make other integrated RIN plot
fig, ax = plt.subplots(figsize=(4.35,2))

ax.plot(RIN_int_pump_values,RIN_int_SHG_calc, label='SHG', color = 'darkorange',linewidth=marksize)
ax.plot(RIN_int_pump_values,RIN_int_SFG_calc, label='SFG', color = 'blue',linewidth=marksize)
ax.plot(RIN_int_pump_values,RIN_int_THG_calc, label='THG', color = 'red', alpha = 0.8, linewidth=marksize)
ax.plot(RIN_int_pump_values,RIN_int_pump_values, label='Pump', color = 'brown',linewidth=marksize)

ax.plot(RIN_int_pump_values,RIN_int_SHG_approx_calc, ls='--', color = 'darkorange', label = r'$4\,\mathrm{RIN}_1$', alpha = 0.8, linewidth=marksize)
ax.plot(RIN_int_pump_values,RIN_int_SFG_sum_p1_p_2, ls='--', color = 'blue', label = r'$\mathrm{RIN}_1 + \mathrm{RIN}_2$', alpha = 0.8, linewidth=marksize)
ax.plot(RIN_int_pump_values,RIN_int_THG_approx_calc, ls='--', color = 'red', label = r'$9\,\mathrm{RIN}_1$', alpha = 0.8, linewidth=marksize)

ax.legend(ncol=2,loc='upper left',fontsize=labelsize, columnspacing = 0.8)

ax.grid()
ax.set_xlim([-50,10])
ax.set_ylim([-50,42])
ax.set_xlabel('Pump Integrated RIN [dBc]', fontweight='bold', fontsize=fontsize,labelpad=3)
ax.set_ylabel('Integrated RIN [dBc]',fontweight='bold', fontsize=fontsize, labelpad=3)

ax.grid(True,which='minor',alpha=0.15)
ax.grid(True,which='major',alpha=0.5)
ax.tick_params(axis='x',labelsize=labelsize)
ax.tick_params(axis='y',labelsize=labelsize)

#Make arrows
ax.annotate('2094 nm\ndata', xy=(RIN_int_pump, RIN_int_pump),xytext=(RIN_int_pump+9, -48.5), arrowprops=dict(arrowstyle='->',color='k',lw=1),fontsize=labelsize)
ax.annotate('1047 nm\ndata', xy=(RIN_int_pump, RIN_int_SHG_data),xytext=(RIN_int_pump+3, RIN_int_SHG_data+15), arrowprops=dict(arrowstyle='->',color='k',lw=1),fontsize=labelsize)
ax.annotate('698 nm\ndata', xy=(RIN_int_pump, RIN_int_THG_data),xytext=(RIN_int_pump-5.5, RIN_int_THG_data+13), arrowprops=dict(arrowstyle='->',color='k',lw=1),fontsize=labelsize)


#Insert experimental datapoints
plt.plot(RIN_int_pump,RIN_int_pump,'.',color='brown')
plt.plot(RIN_int_pump,RIN_int_SHG_data,'.',color='darkorange',linewidth=marksize)
plt.plot(RIN_int_pump,RIN_int_SFG_data,'.',color='blue',linewidth=marksize)
plt.plot(RIN_int_pump,RIN_int_THG_data,'.',color='red',linewidth=marksize)

plt.show()

# plt.savefig(r".\Sup_Int_RIN_spectrum_approx_vs_higher_order.pdf")
# plt.savefig(r".\Sup_Int_RIN_spectrum_approx_vs_higher_order.svg")