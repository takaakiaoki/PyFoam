"""
Application-class that implements pyFoamListCases.py
"""
from optparse import OptionGroup
from os import path,listdir,stat
from glob import glob
from PyFoam.ThirdParty.six.moves import cPickle as pickle
from PyFoam.ThirdParty.six import string_types
import time,datetime
from stat import ST_MTIME
import re
import os

from .PyFoamApplication import PyFoamApplication

from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory
from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile,PyFoamParserError

from PyFoam import configuration

from PyFoam.ThirdParty.six import print_,iteritems,PY3

from PyFoam.Basics.Utilities import humanReadableSize,diskUsage

if PY3:
    long=int

class ListCases(PyFoamApplication):
    def __init__(self,
                 args=None,
                 **kwargs):
        description="""\
List the valid OpenFOAM-cases in a number of directories along with
some basic information (number of timesteps, last timestep,
etc). Currently doesn't honor the parallel data
"""
        PyFoamApplication.__init__(self,
                                   args=args,
                                   description=description,
                                   usage="%prog [<directories>]",
                                   interspersed=True,
                                   changeVersion=False,
                                   nr=0,
                                   exactNr=False,
                                   **kwargs)

    sortChoices=["name","first","last","mtime","nrSteps","procs","diskusage","pFirst","pLast","nrParallel","nowTime","state","lastOutput","startedAt"]

    def addOptions(self):
        what=OptionGroup(self.parser,
                         "What",
                         "Define what should be shown")
        self.parser.add_option_group(what)

        what.add_option("--dump",
                        action="store_true",
                        dest="dump",
                        default=False,
                        help="Dump the information as Python-dictionaries")

        what.add_option("--disk-usage",
                        action="store_true",
                        dest="diskusage",
                        default=False,
                        help="Show the disk-usage of the case (in MB) - may take a long time")

        what.add_option("--parallel-info",
                        action="store_true",
                        dest="parallel",
                        default=False,
                        help="Print information about parallel runs (if present): number of processors and processor first and last time. The mtime will be that of the processor-directories")

        what.add_option("--no-state",
                        action="store_false",
                        dest="state",
                        default=True,
                        help="Don't read state-files")

        what.add_option("--advanced-state",
                        action="store_true",
                        dest="advancedState",
                        default=False,
                        help="Additional state information (run started, last output seen)")

        what.add_option("--estimate-end-time",
                        action="store_true",
                        dest="estimateEndTime",
                        default=False,
                        help="Print an estimated end time (calculated from the start time of the run, the current time and the current simulation time)")

        what.add_option("--start-end-time",
                        action="store_true",
                        dest="startEndTime",
                        default=False,
                        help="Start and end time from the controlDict")

        what.add_option("--custom-data",
                        action="append",
                        dest="customData",
                        default=[],
                        help="Specification of additional data that is read from the pickled data-sets. The format is 'name=spec1::spec2::...' where 'name' is the name under which the data ist shown and 'specN' are the dictionary keys under which the data is accessed. If only 'spec1::spec2::..' is given then a name of the form 'CustomN' will be used. Can be specified more than once")

        what.add_option("--solver-name-for-custom-data",
                        action="store",
                        dest="solverNameForCustom",
                        default=None,
                        help="This is used if '--custom-data' is specified as the data will be searched in 'PyFoamRunner.<solver name>.analyzed'. If unset then the utility will try to automatically determine the name of the solver which might be wrong")

        how=OptionGroup(self.parser,
                         "How",
                         "How the things should be shown")
        self.parser.add_option_group(how)

        how.add_option("--sort-by",
                        type="choice",
                        action="store",
                        dest="sort",
                        default=configuration().get("CommandOptionDefaults","sortListCases",default="name"),
                        choices=self.sortChoices,
                        help="Sort the cases by a specific key (Keys: "+", ".join(self.sortChoices)+") Default: %default")
        how.add_option("--reverse-sort",
                       action="store_true",
                       dest="reverse",
                       default=False,
                       help="Sort in reverse order")
        how.add_option("--relative-times",
                       action="store_true",
                       dest="relativeTime",
                       default=False,
                       help="Show the timestamps relative to the current time")

        behave=OptionGroup(self.parser,
                         "Behaviour",
                         "Additional output etc")
        self.parser.add_option_group(behave)

        behave.add_option("--progress",
                          action="store_true",
                          dest="progress",
                          default=False,
                          help="Print the directories while they are being processed")

    def readState(self,sol,sFile,default=""):
        fName=path.join(sol.name,"PyFoamState."+sFile)
        if not path.exists(fName):
            return default
        else:
            self.hasState=True
            return open(fName).read().strip()

    def run(self):
        dirs=self.parser.getArgs()

        if len(dirs)==0:
            dirs=[path.curdir]

        cData=[]
        totalDiskusage=0
        useSolverInData=False

        self.hasState=False

        customData=[]
        for i,c in enumerate(self.opts.customData):
            lst=c.split("=")
            if len(lst)==2:
                name,spec=lst
                name+="_"  # Make sure that there is no collision with standard-names
            elif len(lst)==1:
                name,spec="Custom%d" % (i+1),c
            else:
                self.error("Custom specification",c,"does not fit the pattern 'name=subs1::subs2::..'")
            customData.append((name,spec.split("::")))

        if len(customData)>0 and not self.opts.solverNameForCustom:
            self.warning("Parameter '--solver-name-for-custom-data' should be set if '--custom-data' is used")
            useSolverInData=True

        for d in dirs:
            for n in listdir(d):
                cName=path.join(d,n)
                if path.isdir(cName):
                    try:
                        sol=SolutionDirectory(cName,archive=None,paraviewLink=False)
                        if sol.isValid():
                            if self.opts.progress:
                                print_("Processing",cName)

                            data={}

                            data["mtime"]=stat(cName)[ST_MTIME]
                            times=sol.getTimes()
                            try:
                                data["first"]=times[0]
                            except IndexError:
                                data["first"]="None"
                            try:
                                data["last"]=times[-1]
                            except IndexError:
                                data["last"]="None"
                            data["nrSteps"]=len(times)
                            data["procs"]=sol.nrProcs()
                            data["pFirst"]=-1
                            data["pLast"]=-1
                            data["nrParallel"]=-1
                            if self.opts.parallel:
                                pTimes=sol.getParallelTimes()
                                data["nrParallel"]=len(pTimes)
                                if len(pTimes)>0:
                                    data["pFirst"]=pTimes[0]
                                    data["pLast"]=pTimes[-1]
                            data["name"]=cName
                            data["diskusage"]=-1
                            if self.opts.diskusage:
                                data["diskusage"]=diskUsage(cName)
                                totalDiskusage+=data["diskusage"]
                            if self.opts.parallel:
                                for f in listdir(cName):
                                    if re.compile("processor[0-9]+").match(f):
                                        data["mtime"]=max(stat(path.join(cName,f))[ST_MTIME],data["mtime"])

                            if self.opts.state:
                                try:
                                    data["nowTime"]=float(self.readState(sol,"CurrentTime"))
                                except ValueError:
                                    data["nowTime"]=None

                                try:
                                    data["lastOutput"]=time.mktime(time.strptime(self.readState(sol,"LastOutputSeen")))
                                except ValueError:
                                    data["lastOutput"]="nix"

                                data["state"]=self.readState(sol,"TheState")

                            if self.opts.state or self.opts.estimateEndTime:
                                try:
                                    data["startedAt"]=time.mktime(time.strptime(self.readState(sol,"StartedAt")))
                                except ValueError:
                                    data["startedAt"]="nix"

                            if self.opts.startEndTime or self.opts.estimateEndTime:
                                try:
                                    ctrlDict=ParsedParameterFile(sol.controlDict(),doMacroExpansion=True)
                                except PyFoamParserError:
                                    # Didn't work with Macro expansion. Let's try without
                                    try:
                                        ctrlDict=ParsedParameterFile(sol.controlDict())
                                    except PyFoamParserError:
                                        ctrlDict=None
                                if ctrlDict:
                                    data["startTime"]=ctrlDict["startTime"]
                                    data["endTime"]=ctrlDict["endTime"]
                                else:
                                    data["startTime"]=None
                                    data["endTime"]=None

                            if self.opts.estimateEndTime:
                                data["endTimeEstimate"]=None
                                if self.readState(sol,"TheState")=="Running":
                                    gone=time.time()-data["startedAt"]
                                    try:
                                        current=float(self.readState(sol,"CurrentTime"))
                                        frac=(current-data["startTime"])/(data["endTime"]-data["startTime"])
                                    except ValueError:
                                        frac=0
                                    if frac>0:
                                        data["endTimeEstimate"]=data["startedAt"]+gone/frac

                            if len(customData)>0:
                                fn=None
                                pickleFile=None
                                if useSolverInData:
                                    data["solver"]="none found"
                                    # try to find the oldest pickled file
                                    for f in ["pickledData","pickledUnfinishedData","pickledStartData"]:
                                        dirAndTime=[]
                                        for g in glob(path.join(cName,"*.analyzed")):
                                            pName=path.join(g,f)
                                            base=path.basename(g)
                                            if base.find("PyFoamRunner.")==0:
                                                solverName=base[len("PyFoamRunner."):-len(".analyzed")]
                                            else:
                                                solverName=None
                                            if path.exists(pName):
                                                dirAndTime.append((path.getmtime(pName),solverName,pName))
                                        dirAndTime.sort(key=lambda x:x[0])
                                        if len(dirAndTime)>0:
                                            data["solver"]=dirAndTime[-1][1]
                                            pickleFile=dirAndTime[-1][2]
                                            break

                                    solverName=data["solver"]
                                else:
                                    solverName=self.opts.solverNameForCustom

                                if pickleFile:
                                    fn=pickleFile
                                else:
                                    for f in ["pickledData","pickledUnfinishedData","pickledStartData"]:
                                        fp=path.join(cName,"PyFoamRunner."+solverName+".analyzed",f)
                                        if path.exists(fp):
                                            fn=fp
                                            break
                                if fn:
                                    raw=pickle.Unpickler(open(fn)).load()
                                    for n,spec in customData:
                                        dt=raw
                                        for k in spec:
                                            try:
                                                dt=dt[k]
                                            except KeyError:
                                                dt="No key '"+k+"'"
                                                break
                                            if isinstance(dt,string_types):
                                                break
                                        data[n]=dt
                                else:
                                    for n,spec in customData:
                                        data[n]="no file"

                            cData.append(data)
                    except OSError:
                        print_(cName,"is unreadable")

        if self.opts.progress:
            print_("Sorting data")


        cData.sort(key=lambda x:x[self.opts.sort],reverse=self.opts.reverse)

        if len(cData)==0:
            print_("No cases found")
            return

        if self.opts.dump:
            print_(cData)
            return

        lens={}
        for k in list(cData[0].keys()):
            lens[k]=len(k)
        for c in cData:
            for k in ["mtime","lastOutput","startedAt","endTimeEstimate"]:
                try:
                    if c[k]!=None:
                        if self.opts.relativeTime:
                            c[k]=datetime.timedelta(seconds=long(time.time()-c[k]))
                        else:
                            c[k]=time.asctime(time.localtime(c[k]))
                except KeyError:
                    pass
                except TypeError:
                    c[k]=None

            try:
                c["diskusage"]=humanReadableSize(c["diskusage"])
            except KeyError:
                pass

            for k,v in iteritems(c):
                lens[k]=max(lens[k],len(str(v)))

        format=""
        spec=["mtime"," | ","first"," - ","last"," (","nrSteps",") "]
        if self.opts.parallel:
            spec+=["| ","procs"," : ","pFirst"," - ","pLast"," (","nrParallel",") | "]
        if self.opts.diskusage:
            spec+=["diskusage"," | "]
        if self.hasState:
            spec+=["nowTime"," s ","state"," | "]
            if self.opts.advancedState:
                spec+=["lastOutput"," | ","startedAt"," | "]
        if self.opts.estimateEndTime:
            if not self.opts.advancedState:
                spec+=["startedAt"," | "]
            spec+=["endTimeEstimate"," | "]
        if self.opts.startEndTime:
            spec+=["startTime"," | ","endTime"," | "]

        if useSolverInData:
            spec+=["solver"," | "]
        for n,s in customData:
            spec+=[n," | "]

        spec+=["name"]

        for i,l in enumerate(spec):
            if  not l in list(cData[0].keys()):
                format+=l
            else:
                if i<len(spec)-1:
                    format+="%%(%s)%ds" % (l,lens[l])
                else:
                    format+="%%(%s)s" % (l)

        if self.opts.progress:
            print_("Printing\n\n")

        header=format % dict(list(zip(list(cData[0].keys()),list(cData[0].keys()))))
        print_(header)
        print_("-"*len(header))

        for d in cData:
            for k in list(d.keys()):
                d[k]=str(d[k])
            print_(format % d)

        if self.opts.diskusage:
            print_("Total disk-usage:",humanReadableSize(totalDiskusage))


# Should work with Python3 and Python2
