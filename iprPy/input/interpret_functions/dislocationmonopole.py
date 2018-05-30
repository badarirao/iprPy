# Standard Python libraries
from __future__ import (absolute_import, print_function,
                        division, unicode_literals)

# http://www.numpy.org/
import numpy as np

# https://github.com/usnistgov/DataModelDict
from DataModelDict import DataModelDict as DM

__all__ = ['dislocationmonopole']

def dislocationmonopole(input_dict, **kwargs):
    """
    Interprets calculation parameters associated with a dislocation-monopole
    record.
    
    The input_dict keys used by this function (which can be renamed using the
    function's keyword arguments):
    
    - **'dislocation_file'** a dislocation-monopole record to load.
    - **'dislocation_content'** alternate file or content to load instead of
      specified dislocation_file.  This is used by prepare functions.
    - **'dislocation_model'** the open DataModelDict of file/content.
    - **'dislocation_family'** the crystal family the defect parameters are specified for.
    - **'a_uvw, b_uvw, c_uvw'** the orientation [uvw] indices. This function only
      reads in values from the surface_model.
    - **'atomshift'** the atomic shift to apply to all atoms.  This function
      only reads in values from the dislocation_model.
    - **'dislocation_burgersvector'** the dislocation's Burgers vector as a
      crystallographic.vector.
    - **'dislocation_boundaryshape'** defines the shape of the boundary
      region.
    - **'dislocation_boundarywidth'** defines the minimum width of the
      boundary region.  This term is in units of the unit cell's a lattice
      parameter.
    - **'ucell'** the unit cell system. Used here in scaling the model
      parameters to the system being explored.
    - **'burgersvector'** the dislocation's Burgers vector as a Cartesian
      vector.
    - **'boundarywidth'** defines the minimum width of the boundary region.
      This term is in length units.
       
    Parameters
    ----------
    input_dict : dict
        Dictionary containing input parameter key-value pairs.
    dislocation_file : str
        Replacement parameter key name for 'dislocation_file'.
    dislocation_content : str
        Replacement parameter key name for 'dislocation_content'.
    dislocation_model : str
        Replacement parameter key name for 'dislocation_model'.
    dislocation_family : str
        Replacement parameter key name for 'dislocation_family'.
    a_uvw : str
        Replacement parameter key name for 'a_uvw'.
    b_uvw : str
        Replacement parameter key name for 'b_uvw'.
    c_uvw : str
        Replacement parameter key name for 'c_uvw'.
    atomshift : str
        Replacement parameter key name for 'atomshift'.
    dislocation_burgersvector : str
        Replacement parameter key name for 'dislocation_burgersvector'.
    dislocation_boundaryshape : str
        Replacement parameter key name for 'dislocation_boundaryshape'.
    dislocation_boundarywidth : str
        Replacement parameter key name for 'dislocation_boundarywidth'.
    ucell : str
        Replacement parameter key name for 'ucell'.
    burgersvector : str
        Replacement parameter key name for 'burgersvector'.
    boundarywidth : str
        Replacement parameter key name for 'boundarywidth'.
    """
    
    # Set default keynames
    keynames = ['dislocation_file', 'dislocation_model', 'dislocation_content',
                'dislocation_family', 'a_uvw', 'b_uvw', 'c_uvw', 'atomshift', 
                'dislocation_burgersvector', 'dislocation_boundaryshape',
                'dislocation_boundarywidth', 'ucell', 'burgersvector',
                'boundarywidth']
    for keyname in keynames:
        kwargs[keyname] = kwargs.get(keyname, keyname)
    
    # Extract input values and assign default values
    dislocation_file = input_dict.get(kwargs['dislocation_file'], None)
    dislocation_content = input_dict.get(kwargs['dislocation_content'], None)
    dislocation_boundaryshape = input_dict.get(kwargs['dislocation_boundaryshape'], 'circle')
    dislocation_boundarywidth = float(input_dict.get(kwargs['dislocation_boundarywidth'], 3.0))
    ucell = input_dict.get(kwargs['ucell'], None)
    
    # Replace defect model with defect content if given
    if dislocation_content is not None:
        dislocation_file = dislocation_content
    
    # If defect model is given
    if dislocation_file is not None:
        
        # Verify competing parameters are not defined
        for key in ('atomshift', 'a_uvw', 'b_uvw', 'c_uvw',
                    'dislocation_burgersvector'):
            assert kwargs[key] not in input_dict, (kwargs[key] + ' and '
                                                   + kwargs['dislocation_file']
                                                   + ' cannot both be supplied')
        
        # Load defect model
        dislocation_model = DM(dislocation_file).find('dislocation-monopole')
        
        # Extract parameter values from defect model
        input_dict[kwargs['dislocation_family']] = dislocation_model['system-family']
        input_dict[kwargs['a_uvw']] = dislocation_model['calculation-parameter']['a_uvw']
        input_dict[kwargs['b_uvw']] = dislocation_model['calculation-parameter']['b_uvw']
        input_dict[kwargs['c_uvw']] = dislocation_model['calculation-parameter']['c_uvw']
        input_dict[kwargs['atomshift']] = dislocation_model['calculation-parameter']['atomshift']
        input_dict[kwargs['dislocation_burgersvector']] = dislocation_model['calculation-parameter']['burgersvector']
    
    # Set default parameter values if defect model not given
    #else: 
    
    # convert parameters if ucell exists
    if ucell is not None:
        dislocation_burgersvector = input_dict[kwargs['dislocation_burgersvector']]
        dislocation_burgersvector = np.array(dislocation_burgersvector.strip().split(),
                                             dtype=float)
        
        # Convert crystallographic vectors to Cartesian vectors
        burgersvector = (dislocation_burgersvector[0] * ucell.box.avect +
                         dislocation_burgersvector[1] * ucell.box.bvect +
                         dislocation_burgersvector[2] * ucell.box.cvect)
        
        # Scale boundary width by unit cell's a lattice constant
        boundarywidth = ucell.box.a * dislocation_boundarywidth
        
    else:
        burgersvector = None
        boundarywidth = None
    
    # Save processed terms
    input_dict[kwargs['dislocation_model']] = dislocation_model
    input_dict[kwargs['dislocation_boundaryshape']] = dislocation_boundaryshape
    input_dict[kwargs['dislocation_boundarywidth']] = dislocation_boundarywidth
    input_dict[kwargs['burgersvector']] = burgersvector
    input_dict[kwargs['boundarywidth']] = boundarywidth