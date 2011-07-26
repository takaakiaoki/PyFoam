#  ICE Revision: $Id: /local/openfoam/Python/PyFoam/PyFoam/__init__.py 7563 2011-07-25T22:14:09.526546Z bgschaid  $ 
""" Utility-classes for OpenFOAM

Module for the Execution of OpenFOAM-commands and processing their output
"""

from Infrastructure.Configuration import Configuration

def version():
    """@return: Version number as a tuple"""
    #    return (0,5,7,"development")
    return (0,5,6)

def versionString():
    """@return: Version number of PyFoam"""
    v=version()

    vStr="%d" % v[0]
    for d in v[1:]:
        if type(d)==int:
            vStr+=(".%d" % d)
        else:
            vStr+=("-%s" % str(d))
    return vStr

def foamVersionString():
    from FoamInformation import foamVersionString
    return foamVersionString()

_configuration = Configuration()

def configuration():
    """@return: The Configuration information of PyFoam"""
    return _configuration

