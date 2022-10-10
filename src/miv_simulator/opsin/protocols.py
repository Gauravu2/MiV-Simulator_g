"""
Stimulation protocols to run on the opsin models
    * Neuro-engineering stimuli: ``step``, ``sinusoid``, ``chirp``, ``ramp``, ``delta``
    * Opsin-specific protocols: ``shortPulse``, ``recovery``.
    * The ``custom`` protocol can be used with arbitrary interpolation fuctions

Based on code from the PyRhO: A Multiscale Optogenetics Simulation Platform
https://github.com/ProjectPyRhO/PyRhO.git
"""

import warnings
import logging
import os
import abc
from collections import OrderedDict
import numpy as np
from scipy.interpolate import InterpolatedUnivariateSpline as spline
from miv_simulator.utils import (
    get_module_logger,
)
from miv_simulator.opsin.core import PyRhOobject

logger = get_module_logger(__name__)


class Protocol(PyRhOobject):  # , metaclass=ABCMeta
    """Common base class for all protocols."""

    __metaclass__ = abc.ABCMeta

    protocol = None
    nRuns = None
    Dt_delay = None
    cycles = None
    Dt_total = None
    dt = None
    phis = None
    Vs = None

    def __init__(self, params=None, saveData=True):
        if params is None:
            params = protParams[self.protocol]
        self.RhO = None
        self.plotPeakRecovery = False
        self.plotStateVars = False
        self.plotKinetics = False
        self.setParams(params)
        self.prepare()
        self.t_start, self.t_end = 0, self.Dt_total
        self.phi_ts = None
        self.lam = 470  # Default wavelength [nm]
        self.PD = None
        self.Ifig = None

    def __str__(self):
        return self.protocol

    def __repr__(self):
        return "<PyRhO {} Protocol object (nRuns={}, nPhis={}, nVs={})>".format(self.protocol, self.nRuns, self.nPhis, self.nVs)

    def __iter__(self):
        """Iterator to return the pulse sequence for the next trial."""
        self.run = 0
        self.phiInd = 0
        self.vInd = 0
        return self

    def __next__(self):
        """Iterator to return the pulse sequence for the next trial."""
        self.run += 1
        if self.run > self.nRuns:
            raise StopIteration
        return self.getRunCycles(self.run - 1)

    def prepare(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """

        if np.isscalar(self.cycles):  # Only 'on' duration specified
            Dt_on = self.cycles
            if hasattr(self, 'Dt_total'):
                Dt_off = self.Dt_total - Dt_on - self.Dt_delay
            else:
                Dt_off = 0
            self.cycles = np.asarray([[Dt_on, Dt_off]])
        elif isinstance(self.cycles, (list, tuple, np.ndarray)):
            if np.isscalar(self.cycles[0]):
                self.cycles = [self.cycles]  # Assume only one pulse
        else:
            raise TypeError('Unexpected type for cycles - expected a list or array!')

        self.cycles = np.asarray(self.cycles)
        self.nPulses = self.cycles.shape[0]
        self.pulses, self.Dt_total = cycles2times(self.cycles, self.Dt_delay)
        self.Dt_delays = np.array([pulse[0] for pulse in self.pulses], copy=True)  # pulses[:,0]    # Delay Durations #self.Dt_delays = np.array([self.Dt_delay] * self.nRuns)
        self.Dt_ons = np.array(self.cycles[:, 0])  # self.Dt_ons = np.array([cycle[0] for cycle in self.cycles])
        self.Dt_offs = np.array(self.cycles[:, 1])  # self.Dt_offs = np.array([cycle[1] for cycle in self.cycles])

        if np.isscalar(self.phis):
            self.phis = [self.phis]  # np.asarray([self.phis])
        self.phis.sort(reverse=True)
        self.nPhis = len(self.phis)

        if np.isscalar(self.Vs):
            self.Vs = [self.Vs]  # np.asarray([self.Vs])
        self.Vs.sort(reverse=True)
        self.nVs = len(self.Vs)

        self.extraPrep()
        return

    def extraPrep(self):
        pass

    def genContainer(self):
        return [[[None for v in range(self.nVs)]
                 for p in range(self.nPhis)]
                for r in range(self.nRuns)]

    def getShortestPeriod(self):
        # min(self.Dt_delay, min(min(self.cycles)))
        return np.amin(self.cycles[self.cycles.nonzero()])

    def finish(self, PC, RhO):
        pass

    def getRunCycles(self, run):
        return (self.cycles, self.Dt_delay)

    def genPulseSet(self, genPulse=None):
        """Function to generate a set of spline functions to phi(t) simulations."""
        if genPulse is None:  # Default to square pulse generator
            genPulse = self.genPulse
        phi_ts = [[[None for pulse in range(self.nPulses)] for phi in range(self.nPhis)] for run in range(self.nRuns)]
        for run in range(self.nRuns):
            cycles, Dt_delay = self.getRunCycles(run)
            pulses, Dt_total = cycles2times(cycles, Dt_delay)
            for phiInd, phi in enumerate(self.phis):
                for pInd, pulse in enumerate(pulses):
                    phi_ts[run][phiInd][pInd] = genPulse(run, phi, pulse)
        self.phi_ts = phi_ts
        return phi_ts

    def genPulse(self, run, phi, pulse):
        """Default interpolation function for square pulses."""
        pStart, pEnd = pulse
        phi_t = spline([pStart, pEnd], [phi, phi], k=1, ext=1)
        return phi_t

    def genPlottingStimuli(self, genPulse=None, vInd=0):
        """Redraw stimulus functions in case data has been realigned."""
        if genPulse is None:
            genPulse = self.genPulse

            # # for Dt_delay in len(self.Dt_delays):
                # # self.Dt_delays -= self.PD.trials[run][phiInd][vInd]
        phi_ts = [[[None for pulse in range(self.nPulses)] for phi in range(self.nPhis)] for run in range(self.nRuns)]
        for run in range(self.nRuns):
            #cycles, Dt_delay = self.getRunCycles(run)
            #pulses, Dt_total = cycles2times(cycles, Dt_delay)
            for phiInd, phi in enumerate(self.phis):
                pc = self.PD.trials[run][phiInd][vInd]
                # if pc.pulseAligned:
                for p, pulse in enumerate(pc.pulses):
                    phi_ts[run][phiInd][p] = genPulse(run, pc.phi, pulse)
        #self.phi_ts = self.genPulseSet()
        return phi_ts

    def getStimArray(self, run, phiInd, dt):  # phi_ts, Dt_delay, cycles, dt):
        """Return a stimulus array (not spline) with the same sampling rate as
        the photocurrent.
        """

        cycles, Dt_delay = self.getRunCycles(run)
        phi_ts = self.phi_ts[run][phiInd][:]

        nPulses = cycles.shape[0]
        assert(len(phi_ts) == nPulses)

        #start, end = RhO.t[0], RhO.t[0]+Dt_delay #start, end = 0.00, Dt_delay
        start, end = 0, Dt_delay
        nSteps = int(round(((end-start)/dt)+1))
        t = np.linspace(start, end, nSteps, endpoint=True)
        phi_tV = np.zeros_like(t)
        #_idx_pulses_ = np.empty([0,2],dtype=int) # Light on and off indexes for each pulse

        for p in range(nPulses):
            start = end
            Dt_on, Dt_off = cycles[p, 0], cycles[p, 1]
            end = start + Dt_on + Dt_off
            nSteps = int(round(((end-start)/dt)+1))
            tPulse = np.linspace(start, end, nSteps, endpoint=True)
            phi_t = phi_ts[p]
            phiPulse = phi_t(tPulse)  # -tPulse[0] # Align time vector to 0 for phi_t to work properly

            #onInd = len(t) - 1 # Start of on-phase
            #offInd = onInd + int(round(Dt_on/dt))
            #_idx_pulses_ = np.vstack((_idx_pulses_, [onInd,offInd]))

            #t = np.r_[t, tPulse[1:]]

            phi_tV = np.r_[phi_tV, phiPulse[1:]]

        phi_tV[np.ma.where(phi_tV < 0)] = 0  # Safeguard for negative phi values
        return phi_tV  #, t, _idx_pulses_

    def plot(self, plotStateVars=False):
        """Plot protocol."""
        import matplotlib.pyplot as plt
        import matplotlib as mpl  # for tick locators

        self.Ifig = plt.figure()
        self.createLayout(self.Ifig)
        self.PD.plot(self.axI)
        self.addAnnotations()
        self.plotExtras()
        self.plotStateVars = plotStateVars
        # TODO: Try producing animated state figures
        # https://jakevdp.github.io/blog/2013/05/28/a-simple-animation-the-magic-triangle/
        #animateStates = True
        if self.plotStateVars:
            #RhO = self.RhO
            for run in range(self.nRuns):
                for phiInd in range(self.nPhis):
                    for vInd in range(self.nVs):
                        pc = self.PD.trials[run][phiInd][vInd]
                        fileName = '{}States{}s-{}-{}-{}'.format(self.protocol, pc.nStates, run, phiInd, vInd)
                        #RhO.plotStates(pc.t, pc.states, pc.pulses, RhO.stateLabels, phi, pc._idx_peaks_, fileName)
                        logger.info('Plotting states to: {}'.format(fileName))
                        pc.plotStates(name=fileName)

        plt.figure(self.Ifig.number)
        plt.sca(self.axI)
        self.axI.set_xlim(self.PD.t_start, self.PD.t_end)
        # if addTitles:
            # figTitle = self.genTitle()
            # plt.title(figTitle) #'Photocurrent through time'

        #self.Ifig.tight_layout()
        plt.tight_layout()
        plt.show()

        figName = os.path.join(config.fDir, self.protocol+self.dataTag+"."+config.saveFigFormat)
        logger.info("Saving figure for {} protocol to {} as {}".format(self.protocol, figName, config.saveFigFormat))
        #externalLegend = False
        #if externalLegend:
        #    self.Ifig.savefig(figName, bbox_extra_artists=(lgd,), bbox_inches='tight', format=config.saveFigFormat) # Use this to save figures when legend is beside the plot
        #else:
        self.Ifig.savefig(figName, format=config.saveFigFormat)
        return

    def createLayout(self, Ifig=None, vInd=0):
        """Create axes for protocols with multiple subplots."""

        import matplotlib.pyplot as plt
        import matplotlib as mpl  # for tick locators

        if Ifig is None:
            Ifig = plt.figure()

        self.addStimulus = config.addStimulus
        #phi_ts = self.genPlottingStimuli()

        # Default layout
        self.axI = Ifig.add_subplot(111)
        plt.sca(self.axI)
        #plotLight(self.pulses, self.axI)

    # TODO: Refactor multiple getLineProps
    def getLineProps(self, run, vInd, phiInd):

        import matplotlib.pyplot as plt
        import matplotlib as mpl  # for tick locators
        
        colours = config.colours
        styles = config.styles

        if config.verbose > 1 and (self.nRuns > len(colours) or len(self.phis) > len(colours) or len(self.Vs) > len(colours)):
            warnings.warn("Warning: only {} line colours are available!".format(len(colours)))
        if config.verbose > 0 and self.nRuns > 1 and len(self.phis) > 1 and len(self.Vs) > 1:
            warnings.warn("Warning: Too many changing variables for one plot!")
        if config.verbose > 2:
            print("Run=#{}/{}; phiInd=#{}/{}; vInd=#{}/{}".format(run, self.nRuns, phiInd, len(self.phis), vInd, len(self.Vs)))
        if self.nRuns > 1:
            col = colours[run % len(colours)]
            if len(self.phis) > 1:
                style = styles[phiInd % len(styles)]
            elif len(self.Vs) > 1:
                style = styles[vInd % len(styles)]
            else:
                style = '-'
        else:
            if len(self.Vs) > 1:
                col = colours[vInd % len(colours)]
                if len(self.phis) > 1:
                    style = styles[phiInd % len(styles)]
                else:
                    style = '-'
            else:
                if len(self.phis) > 1:
                    col = colours[phiInd % len(colours)]
                    style = '-'
                else:
                    col = 'b'    # colours[0]
                    style = '-'  # styles[0]
        return col, style

    def plotExtras(self):
        pass

    def addAnnotations(self):
        pass

    def plotStimulus(self, phi_ts, t_start, pulses, t_end, ax=None, light='shade', col=None, style=None):
        import matplotlib.pyplot as plt
        import matplotlib as mpl  # for tick locators

        nPulses = pulses.shape[0]
        assert(nPulses == len(phi_ts))
        nPoints = 10 * int(round(t_end-t_start / self.dt)) + 1
        t = np.linspace(t_start, t_end, nPoints)

        if ax is None:
            #fig = plt.figure()
            ax = plt.gca()
        else:
            #plt.figure(fig.number)
            plt.sca(ax)

        if col is None:
            for p in range(nPulses):
                plt.plot(t, phi_ts[p](t))
        else:
            if style is None:
                style = '-'
            for p in range(nPulses):
                plt.plot(t, phi_ts[p](t), color=col, linestyle=style)

        if light == 'spectral':
            plotLight(pulses, ax=ax, light='spectral', lam=self.lam)
        else:
            plotLight(pulses, ax=ax, light=light)

        plt.xlabel(r'$\mathrm{Time\ [ms]}$')
        plt.xlim((t_start, t_end))
        plt.ylabel(r'$\mathrm{\phi\ [ph./mm^{2}/s]}$')

        return ax


class protCustom(Protocol):
    """Present a time-varying stimulus defined by a spline function."""
    # Class attributes
    protocol = 'custom'
    squarePulse = False
    # custPulseGenerator = None
    phi_ft = None

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.nRuns = 1  # nRuns ### TODO: Reconsider this...

        #self.custPulseGenerator = self.phi_ft
        if not hasattr(self, 'phi_ts') or self.phi_ts is None:
            #self.phi_ts = self.genPulseSet()
            #self.genPulseSet(self.custPulseGenerator)
            self.genPulseSet(self.phi_ft)

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()

        self.addStimulus = config.addStimulus

        if self.addStimulus:
            # self.genPlottingStimuli(self.custPulseGenerator)
            phi_ts = self.genPlottingStimuli(self.phi_ft)
            gsStim = plt.GridSpec(4, 1)
            self.axS = Ifig.add_subplot(gsStim[0, :])  # Stimulus axes
            self.axI = Ifig.add_subplot(gsStim[1:, :], sharex=self.axS)  # Photocurrent axes
            pc = self.PD.trials[0][0][0]
            plotLight(pc.pulses, ax=self.axS, light='spectral', lam=470, alpha=0.2)
            for run in range(self.nRuns):
                for phiInd in range(self.nPhis):
                    pc = self.PD.trials[run][phiInd][vInd]
                    col, style = self.getLineProps(run, vInd, phiInd)
                    self.plotStimulus(phi_ts[run][phiInd], pc.t_start,
                                      self.pulses, pc.t_end, self.axS,
                                      light=None, col=col, style=style) #light='spectral'
            plt.setp(self.axS.get_xticklabels(), visible=False)
            self.axS.set_xlabel('')
        else:
            self.axI = Ifig.add_subplot(111)

    def plotExtras(self):
        pass


class protStep(Protocol):
    """Present a step (Heaviside) pulse."""
    protocol = 'step'
    squarePulse = True
    nRuns = 1

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.nRuns = 1
        self.phi_ts = self.genPulseSet()

    def addAnnotations(self):
        self.axI.get_xaxis().set_minor_locator(mpl.ticker.AutoMinorLocator())
        self.axI.get_yaxis().set_minor_locator(mpl.ticker.AutoMinorLocator())
        self.axI.grid(b=True, which='minor', axis='both', linewidth=.2)
        self.axI.grid(b=True, which='major', axis='both', linewidth=1)


class protSinusoid(Protocol):
    """Present oscillating stimuli over a range of frequencies to find the
    resonant frequency.
    """
    protocol = 'sinusoid'
    squarePulse = False
    startOn = False
    phi0 = 0

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """

        self.fs = np.sort(np.array(self.fs)) # Frequencies [Hz]
        self.ws = 2 * np.pi * self.fs / (1000) # Frequencies [rads/ms] (scaled from /s to /ms
        self.sr = max(10000, int(round(10*max(self.fs)))) # Nyquist frequency - sampling rate (10*f) >= 2*f >= 10/ms
        #self.dt = 1000/self.sr # dt is set by simulator but used for plotting
        self.nRuns = len(self.ws)

        if (1000)/min(self.fs) > min(self.Dt_ons):
            warnings.warn('Warning: The period of the lowest frequency is longer than the stimulation time!')

        if isinstance(self.phi0, (int, float, complex)):
            self.phi0 = np.ones(self.nRuns) * self.phi0
        elif isinstance(self.phi0, (list, tuple, np.ndarray)):
            if len(self.phi0) != self.nRuns:
                self.phi0 = np.ones(self.nRuns) * self.phi0[0]
        else:
            warnings.warn('Unexpected data type for phi0: ', type(self.phi0))

        assert(len(self.phi0) == self.nRuns)

        self.t_start, self.t_end = 0, self.Dt_total
        self.phi_ts = self.genPulseSet()
        self.runLabels = [r'$f={}\mathrm{{Hz}}$ '.format(round_sig(f, 3)) for f in self.fs]

    def getShortestPeriod(self):
        return 1000/self.sr  # dt [ms]

    def genPulse(self, run, phi, pulse):
        pStart, pEnd = pulse
        Dt_on = pEnd - pStart
        t = np.linspace(0.0, Dt_on, int(round((Dt_on*self.sr/1000))+1), endpoint=True)  # Create smooth series of time points to interpolate between
        if self.startOn:  # Generalise to phase offset
            phi_t = spline(pStart + t, self.phi0[run] + 0.5*phi*(1+np.cos(self.ws[run]*t)), ext=1, k=5)
        else:
            phi_t = spline(pStart + t, self.phi0[run] + 0.5*phi*(1-np.cos(self.ws[run]*t)), ext=1, k=5)

        return phi_t

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()

        self.addStimulus = config.addStimulus

        if self.nRuns > 1:  #len(phis) > 1:
            gsSin = plt.GridSpec(2, 3)
            self.axIp = Ifig.add_subplot(gsSin[0, -1])
            self.axIss = Ifig.add_subplot(gsSin[1, -1], sharex=self.axIp)
            self.axI = Ifig.add_subplot(gsSin[:, :-1])
        else:
            self.addStimulus = config.addStimulus

            if self.addStimulus:
                phi_ts = self.genPlottingStimuli()

                gsStim = plt.GridSpec(4, 1)
                self.axS = Ifig.add_subplot(gsStim[0, :])  # Stimulus axes
                self.axI = Ifig.add_subplot(gsStim[1:, :], sharex=self.axS)  # Photocurrent axes
                for run in range(self.nRuns):
                    for phiInd in range(self.nPhis):
                        pc = self.PD.trials[run][phiInd][vInd]
                        col, style = self.getLineProps(run, vInd, phiInd)
                        self.plotStimulus(phi_ts[run][phiInd], pc.t_start, pc.pulses, pc.t_end, self.axS, light='spectral', col=col, style=style)
                plt.setp(self.axS.get_xticklabels(), visible=False)
                self.axS.set_xlabel('')  # plt.xlabel('')
                self.axS.set_ylim(self.phi0[0], max(self.phis))  # phi0[r]
                if max(self.phis) / min(self.phis) >= 100:
                    self.axS.set_yscale('log')  # plt.yscale('log')
            else:
                self.axI = Ifig.add_subplot(111)

    def plotExtras(self):
        splineOrder = 2  # [1,5]
        trim = 0.1
        transEndInd = int(self.Dt_delays[0] + round(self.Dt_ons[0] * trim / self.dt))

        if self.nRuns > 1:
            #plt.figure(Ifig.number)
            #axI.legend().set_visible(False)

            #if len(self.phis) > 1:
            fstars = np.zeros((self.nPhis, self.nVs))
            for phiInd, phiOn in enumerate(self.phis):  # TODO: These loops need reconsidering...!!!
                for vInd, V in enumerate(self.Vs):
                    Ipeaks = np.zeros(self.nRuns)
                    for run in range(self.nRuns):
                        PC = self.PD.trials[run][phiInd][vInd]
                        Ipeaks[run] = abs(PC.I_peak_) # Maximum absolute value over all peaks from that trial
                        Ip = self.PD.trials[np.argmax(Ipeaks)][phiInd][vInd].I_peak_
                    col, style = self.getLineProps(run, vInd, phiInd)
                    self.axIp.plot(self.fs, Ipeaks, 'x', color=col)
                    try:
                        intIp = spline(self.fs, Ipeaks, k=splineOrder)
                        #nPoints = 10*int(round(abs(np.log10(self.fs[-1])-np.log10(self.fs[0]))+1))
                        fsmooth = np.logspace(np.log10(self.fs[0]),
                                              np.log10(self.fs[-1]), num=1001)
                        self.axIp.plot(fsmooth, intIp(fsmooth))
                    except:
                        if config.verbose > 0:
                            print('Unable to plot spline for current peaks!')
                    fstar_p = self.fs[np.argmax(Ipeaks)]
                    fstars[phiInd, vInd] = fstar_p
                    Ap = max(Ipeaks)
                    #fpLabel = r'$f^*_{{peak}}={}$ $\mathrm{{[Hz]}}$'.format(round_sig(fstar_p,3))
                    self.axIp.plot(fstar_p, Ap, '*', markersize=10)
                    #axIp.annotate(fpLabel, xy=(fstar_p,Ap), xytext=(0.7, 0.9), textcoords='axes fraction', arrowprops={'arrowstyle':'->','color':'black'})

            self.axIp.set_xscale('log')
            self.axIp.set_ylabel(r'$|A|_{peak}$ $\mathrm{[nA]}$')
            if config.addTitles:
                #self.axIp.set_title('$\mathrm{|Amplitude|_{peak}\ vs.\ frequency}.\ f^*:=arg\,max_f(|A|)$')
                self.axIp.set_title(r'$f^*:=arg\,max_f(|A|_{peak})$')
            #axIp.set_aspect('auto')

            # Calculate the time to allow for transition effects from the period of fstar_p
            # buffer = 3
            # fstar_p = max(max(fstars))
            # transD = buffer * np.ceil(1000/fstar_p) # [ms]
            # transEndInd = round((self.Dt_delays[0]+transD)/self.dt)
            # if transEndInd >= (self.Dt_ons[0])/self.dt: # If transition period is greater than the on period
                # transEndInd = round((self.Dt_delays[0]+self.Dt_ons[0]/2)/self.dt) # Take the second half of the data

            tTransEnd = transEndInd * self.dt #ts[0][0][0]
            self.axI.axvline(x=tTransEnd, linestyle=':', color='k')
            arrow = {'arrowstyle': '<->', 'color': 'black', 'shrinkA': 0, 'shrinkB': 0}
            for phiInd, phiOn in enumerate(self.phis):  # TODO: These loops need reconsidering...!!!
                for vInd, V in enumerate(self.Vs):
                    PC = self.PD.trials[np.argmax(Ipeaks)][phiInd][vInd]
                    onBegInd, onEndInd = PC._idx_pulses_[0]
                    t = PC.t
                    self.axI.annotate('', xy=(tTransEnd, Ip), xytext=(t[onEndInd], Ip),
                                      arrowprops=arrow)

            for phiInd, phiOn in enumerate(self.phis):
                for vInd, V in enumerate(self.Vs):
                    Iabs = np.zeros(self.nRuns)  # [None for r in range(nRuns)]
                    for run in range(self.nRuns):
                        PC = self.PD.trials[run][phiInd][vInd]
                        onBegInd, onEndInd = PC._idx_pulses_[0]
                        t = PC.t  # t = ts[run][phiInd][vInd]
                        I_RhO = PC.I  # I_RhO = Is[run][phiInd][vInd]
                        #transEndInd = np.searchsorted(t,Dt_delay+transD,side="left") # Add one since upper bound is not included in slice
                        #if transEndInd >= len(t): # If transition period is greater than the on period
                        #    transEndInd = round(len(t[onBegInd:onEndInd+1])/2) # Take the second half of the data
                        #print(fstar_p,'Hz --> ',transD,'ms;', transEndInd,':',onEndInd+1)
                        I_zone = I_RhO[transEndInd:onEndInd+1]
                        try:
                            maxV = max(I_zone)
                        except ValueError:
                            maxV = 0.0
                        try:
                            minV = min(I_zone)
                        except ValueError:
                            minV = 0.0
                        Iabs[run] = abs(maxV-minV)

                    #axI.axvline(x=t[transEndInd],linestyle=':',color='k')
                    #axI.annotate('Search zone', xy=(t[transEndInd], min(I_RhO)), xytext=(t[onEndInd], min(I_RhO)), arrowprops={'arrowstyle':'<->','color':'black'})
                    col, style = self.getLineProps(run, vInd, phiInd)  # TODO: Modify to match colours correctly
                    self.axIss.plot(self.fs, Iabs, 'x', color=col)
                    try:
                        intIss = spline(self.fs, Iabs, k=splineOrder)
                        #fsmooth = np.logspace(self.fs[0], self.fs[-1], 100)
                        self.axIss.plot(fsmooth, intIss(fsmooth))
                    except:
                        if config.verbose > 0:
                            print('Unable to plot spline for current steady-states!')
                    fstar_abs = self.fs[np.argmax(Iabs)]
                    fstars[phiInd,vInd] = fstar_abs
                    Aabs = max(Iabs)
                    fabsLabel = r'$f^*_{{res}}={}$ $\mathrm{{[Hz]}}$'.format(round_sig(fstar_abs,3))
                    self.axIss.plot(fstar_abs, Aabs, '*', markersize=10, label=fabsLabel)
                    self.axIss.legend(loc='best')
                    #axIss.annotate(fabsLabel, xy=(fstar_abs,Aabs), xytext=(0.7, 0.9), textcoords='axes fraction', arrowprops={'arrowstyle':'->','color':'black'})
                    if config.verbose > 0:
                        print('Resonant frequency (phi={}; V={}) = {} Hz'.format(phiOn, V, fstar_abs))
            self.axIss.set_xscale('log')
            self.axIss.set_xlabel(r'$f$ $\mathrm{[Hz]}$')
            self.axIss.set_ylabel(r'$|A|_{ss}$ $\mathrm{[nA]}$')
            if config.addTitles:
                #axIss.set_title('$\mathrm{|Amplitude|_{ss}\ vs.\ frequency}.\ f^*:=arg\,max_f(|A|)$')
                self.axIss.set_title(r'$f^*:=arg\,max_f(|A|_{ss})$')

            plt.tight_layout()

            self.fstars = fstars
            if len(self.phis) > 1:  # Multiple light amplitudes
                #for i, phi0 in enumerate(self.phi0):
                fstarAfig = plt.figure()
                for vInd, V in enumerate(self.Vs):
                    if self.phi0[0] > 0:  # phi0[r]
                        plt.plot(np.array(self.phis)/self.phi0[0], fstars[:, vInd])
                        plt.xlabel(r'$\mathrm{Modulating}\ \phi(t)/\phi_0$')
                    else:
                        plt.plot(np.array(self.phis), fstars[:,vInd])
                        plt.xlabel(r'$\mathrm{Modulating}\ \phi(t)$')
                plt.xscale('log')
                plt.ylabel(r'$f^*\ \mathrm{[Hz]}$')
                if config.addTitles:
                    plt.title(r'$f^*\ vs.\ \phi_1(t).\ \mathrm{{Background\ illumination:}}\ \phi_0(t)={:.3g}$'.format(self.phi0[0]))



class protChirp(Protocol):
    """Sweep through a range of frequencies from f0 to fT either linearly or exponentially"""
    protocol = 'chirp'
    squarePulse = False
    f0 = 0
    fT = 0
    linear = True
    startOn = False
    phi0 = 0

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """

        self.sr = max(10000, int(round(10 * max(self.f0, self.fT)))) # Nyquist frequency - sampling rate (10*f) >= 2*f
        self.nRuns = 1  # len(self.ws)
        #self.cycles = np.column_stack((self.Dt_ons,self.Dt_offs))
        #ws = 2 * np.pi * np.logspace(-4,10,num=7) # Frequencies [rads/s]

        if (1000)/self.f0 > min(self.Dt_ons):  # 1/10**self.fs[0] > self.Dt_total:
            warnings.warn('Warning: The period of the lowest frequency is longer than the stimulation time!')

        if isinstance(self.phi0, (int, float, complex)):
            self.phi0 = np.ones(self.nRuns) * self.phi0
        elif isinstance(self.phi0, (list, tuple, np.ndarray)):
            if len(self.phi0) != self.nRuns:
                self.phi0 = np.ones(self.nRuns) * self.phi0[0]
        else:
            warnings.warn('Unexpected data type for phi0: ', type(self.phi0))

        assert(len(self.phi0) == self.nRuns)

        self.phi_ts = self.genPulseSet()

    def getShortestPeriod(self):
        return 1000/self.sr

    def genPulse(self, run, phi, pulse):
        pStart, pEnd = pulse
        Dt_on = pEnd - pStart
        t = np.linspace(0.0, Dt_on, (Dt_on*self.sr/1000)+1, endpoint=True)  # Create smooth series of time points to interpolate between
        if self.linear:  # Linear sweep
            ft = self.f0 + (self.fT-self.f0)*(t/Dt_on)
        else:           # Exponential sweep
            ft = self.f0 * (self.fT/self.f0)**(t/Dt_on)
        ft /= 1000  # Convert to frequency in ms
        if self.startOn:
            phi_t = spline(pStart + t, self.phi0[run] + 0.5*phi*(1+np.cos(ft*t)), ext=1, k=5)
        else:
            phi_t = spline(pStart + t, self.phi0[run] + 0.5*phi*(1-np.cos(ft*t)), ext=1, k=5)
        return phi_t

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()

        self.addStimulus = config.addStimulus

        if self.addStimulus:
            phi_ts = self.genPlottingStimuli()
            gsStim = plt.GridSpec(4, 1)
            self.axS = Ifig.add_subplot(gsStim[0, :]) # Stimulus axes
            self.axI = Ifig.add_subplot(gsStim[1:, :], sharex=self.axS)  # Photocurrent axes
            for run in range(self.nRuns):
                for phiInd in range(self.nPhis):
                    pc = self.PD.trials[run][phiInd][vInd]
                    col, style = self.getLineProps(run, vInd, phiInd)
                    self.plotStimulus(phi_ts[run][phiInd], pc.t_start, pc.pulses, pc.t_end, self.axS, light='spectral', col=col, style=style)
            plt.setp(self.axS.get_xticklabels(), visible=False)
            self.axS.set_xlabel('')  # plt.xlabel('')

            self.axS.set_ylim(self.phi0[0], max(self.phis))  # phi0[r]

            if max(self.phis) / min(self.phis) >= 100:
                self.axS.set_yscale('log')  # plt.yscale('log')

            # Overlay instantaneous frequency
            self.axF = self.axS.twinx()
            if not self.linear:
                self.axF.set_yscale('log')
            pc = self.PD.trials[0][0][0]
            for p in range(self.nPulses):
                pStart, pEnd = self.PD.trials[0][0][0].pulses[p]
                Dt_on = pEnd - pStart
                nPoints = 10 * int(round(Dt_on / self.dt)) + 1  # 10001
                tsmooth = np.linspace(0, Dt_on, nPoints)

                if self.linear:
                    ft = self.f0 + (self.fT-self.f0)*(tsmooth/Dt_on)
                else:  # Exponential
                    ft = self.f0 * (self.fT/self.f0)**(tsmooth/Dt_on)
                self.axF.plot(tsmooth+pStart, ft, 'g')
            self.axF.set_ylabel(r'$f\ \mathrm{[Hz]}$')
        else:
            self.axI = Ifig.add_subplot(111)

        #plotLight(self.pulses, self.axI)


class protRamp(Protocol):
    """Linearly increasing pulse."""
    protocol = 'ramp'
    squarePulse = False
    nRuns = 1
    phi0 = 0

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.nRuns = 1  # nRuns # Make len(phi_ton)?
        self.cycles = np.column_stack((self.Dt_ons,self.Dt_offs))
        self.phi_ts = self.genPulseSet()

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()

        self.addStimulus = config.addStimulus

        if self.addStimulus:
            phi_ts = self.genPlottingStimuli()
            gsStim = plt.GridSpec(4, 1)
            self.axS = Ifig.add_subplot(gsStim[0, :])  # Stimulus axes
            self.axI = Ifig.add_subplot(gsStim[1:, :], sharex=self.axS)  # Photocurrent axes
            pc = self.PD.trials[0][0][0]
            plotLight(pc.pulses, ax=self.axS, light='spectral', lam=470, alpha=0.2)
            #for p in range(self.nPulses):
            for run in range(self.nRuns):
                for phiInd in range(self.nPhis):
                    pc = self.PD.trials[run][phiInd][vInd]
                    col, style = self.getLineProps(run, vInd, phiInd)
                    self.plotStimulus(phi_ts[run][phiInd], pc.t_start, self.pulses, pc.t_end, self.axS, light=None, col=col, style=style) #light='spectral'
            plt.setp(self.axS.get_xticklabels(), visible=False)
            #plt.xlabel('')
            self.axS.set_xlabel('')
            #if phis[-1]/phis[0] >= 100:
            #    plt.yscale('log')
        else:
            self.axI = Ifig.add_subplot(111)

    def genPulse(self, run, phi, pulse):
        """Generate spline for a particular pulse. phi0 is the offset so
        decreasing ramps can be created with negative phi values.
        """
        pStart, pEnd = pulse
        phi_t = spline([pStart, pEnd], [self.phi0, self.phi0+phi], k=1, ext=1)
        return phi_t


class protDelta(Protocol):
    # One very short, saturation intensity pulse e.g. 10 ns @ 100 mW*mm^-2 for wild type ChR
    # Used to calculate gbar, assuming that O(1)-->1 as Dt_on-->0 and phi-->inf
    protocol = 'delta'
    squarePulse = True
    nRuns = 1
    Dt_on = 0

    def prepare(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        assert(self.Dt_total >= self.Dt_delay + self.Dt_on)  # ==> Dt_off >= 0
        self.cycles = np.asarray([[self.Dt_on, self.Dt_total-self.Dt_delay-self.Dt_on]])
        self.nPulses = self.cycles.shape[0]
        self.pulses, self.Dt_total = cycles2times(self.cycles, self.Dt_delay)
        self.Dt_delays = np.array([row[0] for row in self.pulses], copy=True)  # pulses[:,0]    # Delay Durations
        self.Dt_ons = [row[1]-row[0] for row in self.pulses]  # pulses[:,1] - pulses[:,0]   # Pulse Durations
        self.Dt_offs = np.append(self.pulses[1:, 0], self.Dt_total) - self.pulses[:, 1]

        if np.isscalar(self.phis):
            self.phis = np.asarray([self.phis])
        self.phis.sort(reverse=True)
        self.nPhis = len(self.phis)

        if np.isscalar(self.Vs):
            self.Vs = np.asarray([self.Vs])
        self.Vs.sort(reverse=True)
        self.nVs = len(self.Vs)

        self.addStimulus = config.addStimulus
        self.extraPrep()
        return

    def extraPrep(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.nRuns = 1
        self.phi_ts = self.genPulseSet()

    def finish(self, PC, RhO):
        # Take the max over all runs, phis and Vs?
        # Ipmax = minmax(self.IpVals[run][phiInd][vInd][:])# = I_RhO[peakInds]
        if PC.V is None:
            return
        try:  # if V != RhO.E:
            Gmax = PC.I_peak_ / (PC.V - RhO.E)  # Ipmax / (V - RhO.E) # Assuming [O_p] = 1 ##### Should fV also be used?
        except ZeroDivisionError:
            print("The clamp voltage must be different to the reversal potential!")
        gbar_est = Gmax * 1e6
        if config.verbose > 0:
            print("Estimated maximum conductance (g) = {} uS".format(round_sig(gbar_est, 3)))

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()
        if self.addStimulus:
            phi_ts = self.genPlottingStimuli()
            gsStim = plt.GridSpec(4, 1)
            self.axS = Ifig.add_subplot(gsStim[0, :])  # Stimulus axes
            self.axI = Ifig.add_subplot(gsStim[1:, :], sharex=self.axS)  # Photocurrent axes
            for run in range(self.nRuns):
                for phiInd in range(self.nPhis):
                    pc = self.PD.trials[run][phiInd][vInd]
                    col, style = self.getLineProps(run, vInd, phiInd)
                    self.plotStimulus(phi_ts[run][phiInd], pc.t_start, pc.pulses, pc.t_end, self.axS, light='spectral', col=col, style=style)
            plt.setp(self.axS.get_xticklabels(), visible=False)
            self.axS.set_xlabel('')
            if max(self.phis) / min(self.phis) >= 100:
                self.axS.set_yscale('log')
        else:
            self.axI = Ifig.add_subplot(111)
        #plotLight(self.pulses, self.axI)

    def addAnnotations(self):
        #plt.figure(Ifig.number)
        for run in range(self.nRuns):
            for phiInd in range(self.nPhis):
                for vInd in range(self.nVs):
                    pc = self.PD.trials[run][phiInd][vInd]
                    # Maximum only...
                    #Ip = pc.I_peak_
                    #tp = pc.t_peak_
                    toffset = round(0.1 * pc.t_end)
                    for p in range(self.nPulses):
                        if pc.I_peaks_[p] is not None:
                            Ip = pc.I_peaks_[p]
                            tp = pc.t_peaks_[p]
                            tlag = pc.Dt_lags_[p]

                            self.axI.annotate(r'$I_{{peak}} = {:.3g}\mathrm{{nA}};\ t_{{lag}} = {:.3g}\mathrm{{ms}}$'.format(Ip, tlag),
                                        xy=(tp, Ip), xytext=(toffset+tp, Ip),
                                        arrowprops=dict(arrowstyle="wedge,tail_width=0.6", shrinkA=5, shrinkB=15, facecolor=config.colours[2]),
                                        horizontalalignment='left', verticalalignment='center', fontsize=config.eqSize)

                            self.axI.axvline(x=tp, linestyle=':', color='k')
                            #plt.axhline(y=I_RhO[peakInds[0]], linestyle=':', color='k')
                            #label = r'$I_{{peak}} = {:.3g}\mathrm{{nA;}}\ t_{{lag}} = {:.3g}\mathrm{{ms}}$'.format(Ip, tlag)
                            #plt.text(1.05*tp, 1.05*Ip, label, ha='left', va='bottom', fontsize=config.eqSize)
        #ymin, ymax = self.axI.get_ylim()
        #self.axI.set_ylim(ymin, ymax, auto=True)
        plt.tight_layout()

        
class protShortPulse(Protocol):
    # Vary pulse length - See Nikolic et al. 2009, Fig. 2 & 9
    protocol = 'shortPulse'
    squarePulse = True
    nPulses = 1  # Fixed at 1

    def prepare(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.pDs = np.sort(np.array(self.pDs))
        self.nRuns = len(self.pDs)
        self.Dt_delays = np.ones(self.nRuns)*self.Dt_delay
        self.Dt_ons = self.pDs
        self.Dt_offs = (np.ones(self.nRuns)*self.Dt_total) - self.Dt_delays - self.Dt_ons
        self.cycles = np.column_stack((self.Dt_ons, self.Dt_offs))
        self.phis.sort(reverse=True)
        self.Vs.sort(reverse=True)
        self.nPhis = len(self.phis)
        self.nVs = len(self.Vs)
        self.phi_ts = self.genPulseSet()
        self.runLabels = [r'$\mathrm{{Pulse}}={}\mathrm{{ms}}$ '.format(pD) for pD in self.pDs]

    def getRunCycles(self, run):
        return (np.asarray([[self.Dt_ons[run], self.Dt_offs[run]]]),
                self.Dt_delays[run])

    def createLayout(self, Ifig=None, vInd=0):
        if Ifig is None:
            Ifig = plt.figure()
        self.addStimulus = config.addStimulus
        gsPL = plt.GridSpec(2, 3)
        self.axLag = Ifig.add_subplot(gsPL[0, -1])
        self.axPeak = Ifig.add_subplot(gsPL[1, -1], sharex=self.axLag)
        self.axI = Ifig.add_subplot(gsPL[:, :-1])

    def addAnnotations(self):
        # Freeze axis limits
        ymin, ymax = self.axI.get_ylim()
        pos = 0.02 * abs(ymax-ymin)
        self.axI.set_ylim(ymin, ymax + round(pos*(self.nRuns+1)), auto=True)

        lightBarWidth = 2 * mpl.rcParams['lines.linewidth']
        peakMarkerSize = 1.5 * mpl.rcParams['lines.markersize']

        for run in range(self.nRuns):
            for phiInd in range(self.nPhis):
                for vInd in range(self.nVs):
                    colour, style = self.getLineProps(run, vInd, phiInd)
                    PC = self.PD.trials[run][phiInd][vInd]
                    t_on, t_off = PC.pulses[0, :]

                    self.axI.hlines(y=ymax+(run+1)*pos, xmin=t_on, xmax=t_off,
                                    lw=lightBarWidth, color=colour)
                    self.axI.axvline(x=t_on, linestyle=':', c='k', label='_nolegend_')
                    self.axI.axvline(x=t_off, linestyle=':', c=colour, label='_nolegend_')

                    self.axI.plot(PC.t_peaks_, PC.I_peaks_, marker='*',
                                  ms=peakMarkerSize, c=colour)

                    # Plot t_peak vs t_off c.f. Nikolic et al. 2009 Fig 2b
                    self.axLag.plot(self.pDs[run], PC.Dt_lags_[0], marker='*',
                                    ms=peakMarkerSize, c=colour)

                    # Plot I_peak vs t_off c.f. Nikolic et al. 2009 Fig 2c
                    self.axPeak.plot(self.pDs[run], PC.I_peaks_, marker='*',
                                     ms=peakMarkerSize, c=colour)

        # axLag.axis('equal')
        tmax = max(self.pDs)*1.25
        self.axLag.plot([0, tmax], [0, tmax], ls="--", c=".3")
        self.axLag.set_xlim(0, tmax)
        self.axLag.set_ylim(0, tmax)
        self.axLag.set_ylabel(r'$\mathrm{Time\ of\ peak\ [ms]}$')
        self.axLag.set_aspect('auto')
        self.axPeak.set_xlim(0, tmax)
        self.axPeak.set_xlabel(r'$\mathrm{Pulse\ duration\ [ms]}$')
        self.axPeak.set_ylabel(r'$\mathrm{Photocurrent\ peak\ [nA]}$')


class protRecovery(Protocol):
    '''Two pulse stimulation protocol with varying inter-pulse interval to
    determine the dark recovery rate.
    '''
    # Vary Inter-Pulse-Interval
    protocol = 'recovery'
    squarePulse = True
    nPulses = 2  # Fixed at 2 for this protocol

    Dt_on = 0
    # def __next__(self):
        # if self.run >= self.nRuns:
            # raise StopIteration
        # return np.asarray[self.pulses[self.run]]

    def prepare(self):
        """Function to set-up additional variables and make parameters
        consistent after any changes.
        """
        self.Dt_IPIs = np.sort(np.asarray(self.Dt_IPIs))

        self.nRuns = len(self.Dt_IPIs)
        self.Dt_delays = np.ones(self.nRuns)*self.Dt_delay
        self.Dt_ons = np.ones(self.nRuns)*self.Dt_on
        self.Dt_offs = self.Dt_IPIs
        # [:,0] = on phase duration; [:,1] = off phase duration
        self.cycles = np.column_stack((self.Dt_ons, self.Dt_offs))

        self.pulses, _ = cycles2times(self.cycles, self.Dt_delay)
        self.runCycles = np.zeros((self.nPulses, 2, self.nRuns))
        for run in range(self.nRuns):
            self.runCycles[:, :, run] = np.asarray([[self.Dt_ons[run], self.Dt_offs[run]],
                                                    [self.Dt_ons[run], self.Dt_offs[run]]])

        self.t_start = 0
        self.t_end = self.Dt_total
        IPIminD = max(self.Dt_delays) + (2*max(self.Dt_ons)) + max(self.Dt_IPIs)
        if self.t_end < IPIminD:
            warnings.warn("Insufficient run time for all stimulation periods!")
        else:
            self.runCycles[-1, 1, :] = self.Dt_total - IPIminD

        self.IpIPI = np.zeros(self.nRuns)
        self.tpIPI = np.zeros(self.nRuns)

        if np.isscalar(self.phis):
            self.phis = np.asarray([self.phis])
        self.phis.sort(reverse=True)
        self.nPhis = len(self.phis)

        if np.isscalar(self.Vs):
            self.Vs = np.asarray([self.Vs])
        self.Vs.sort(reverse=True)
        self.nVs = len(self.Vs)

        self.phi_ts = self.genPulseSet()
        self.runLabels = [r'$\mathrm{{IPI}}={}\mathrm{{ms}}$ '.format(IPI)
                          for IPI in self.Dt_IPIs]

    def getRunCycles(self, run):
        return self.runCycles[:, :, run], self.Dt_delays[run]

    def fitParams(self):
        self.PD.params = [[None for vInd in range(self.nVs)] for phiInd in range(self.nPhis)]
        for phiInd in range(self.nPhis):
            for vInd in range(self.nVs):
                # Fit peak recovery
                t_peaks, I_peaks, Ipeak0, Iss0 = getRecoveryPeaks(self.PD, phiInd, vInd, usePeakTime=True)
                params = Parameters()
                params.add('Gr0', value=0.002, min=0.0001, max=0.1)
                params = fitRecovery(t_peaks, I_peaks, params, Ipeak0, Iss0)
                if config.verbose > 0:
                    Gr0 = params['Gr0'].value
                    print("tau_r0 = {} ==> G_r0 = {}".format(1/Gr0, Gr0))
                self.PD.params[phiInd][vInd] = params

    def finish(self, PC, RhO):
        # Build array of second peaks
        self.PD.IPIpeaks_ = np.zeros((self.nRuns, self.nPhis, self.nVs))
        self.PD.tIPIpeaks_ = np.zeros((self.nRuns, self.nPhis, self.nVs))
        for run in range(self.nRuns):
            for phiInd in range(self.nPhis):
                for vInd in range(self.nVs):
                    PC = self.PD.trials[run][phiInd][vInd]
                    PC.align_to(PC.pulses[0, 1])  # End of the first pulse
                    self.PD.IPIpeaks_[run][phiInd][vInd] = PC.I_peaks_[1]
                    self.PD.tIPIpeaks_[run][phiInd][vInd] = PC.t_peaks_[1]

        if config.verbose > 1:
            print(self.PD.tIPIpeaks_)
            print(self.PD.IPIpeaks_)

        self.fitParams()

    def addAnnotations(self):
        # Freeze axis limits
        ymin, ymax = plt.ylim()
        pos = 0.02 * abs(ymax-ymin)
        plt.ylim(ymin, pos*self.nRuns)
        xmin, xmax = plt.xlim()
        plt.xlim(xmin, xmax)
        for run in range(self.nRuns):
            for phiInd in range(self.nPhis):
                for vInd in range(self.nVs):
                    col, style = self.getLineProps(run, vInd, phiInd)
                    arrow = {'arrowstyle': '<->', 'color': col,
                             'shrinkA': 0, 'shrinkB': 0}
                    pulses = self.PD.trials[run][phiInd][vInd].pulses
                    plt.annotate('', (pulses[0, 1], (run+1)*pos),
                                 (pulses[1, 0], (run+1)*pos), arrowprops=arrow)
                    # TODO: Refactor this to use self.fitParams
                    if run == 0:  # Fit peak recovery
                        t_peaks, I_peaks, Ipeak0, Iss0 = getRecoveryPeaks(self.PD, phiInd, vInd, usePeakTime=True)
                        params = Parameters()
                        params.add('Gr0', value=0.002, min=0.0001, max=0.1)
                        params = fitRecovery(t_peaks, I_peaks, params, Ipeak0, Iss0, self.axI)
                        if config.verbose > 0:
                            Gr0 = params['Gr0'].value
                            print("tau_r0 = {} ==> G_r0 = {}".format(1/Gr0, Gr0))
        return


protocols = OrderedDict([('step', protStep),
                         ('delta', protDelta),
                         ('sinusoid', protSinusoid),
                         ('chirp', protChirp),
                         ('ramp', protRamp),
                         ('recovery', protRecovery),
                         ('shortPulse', protShortPulse),
                         ('custom', protCustom)])

# E.g.
# protocols['shortPulse']([1e12], [-70], 25, [1,2,3,5,8,10,20], 100, 0.1)

# squarePulses = [protocol for protocol in protocols if protocol.squarePulse]
# arbitraryPulses = [protocol for protocol in protocols if not protocol.squarePulse]
# squarePulses = {'custom': True, 'delta': True, 'step': True, 'rectifier': True, 'shortPulse': True, 'recovery': True}
# arbitraryPulses = {'custom': True, 'sinusoid': True, 'chirp': True, 'ramp':True} # Move custom here
# smallSignalAnalysis = {'sinusoid': True, 'step': True, 'delta': True}


def selectProtocol(protocol, params=None):
    """Protocol selection function"""
    if protocol in protList:
        if params:
            return protocols[protocol](params)
        else:
            return protocols[protocol](params=protParams[protocol])
    else:
        raise NotImplementedError(protocol)
