#!/usr/bin/env python
import os
import sys
import random
import matplotlib.pyplot as plt
import numpy as np
import uuid
from copy import deepcopy

import iprPy
from DataModelDict import DataModelDict as DM
import atomman as am
import atomman.lammps as lmp
import atomman.unitconvert as uc

__calc_name__ = os.path.splitext(os.path.basename(__file__))[0]

def main(*args):    
    """Main function for running calculation"""

    #Read in parameters from input file
    with open(args[0]) as f:
        input_dict = input(f, *args[1:])
       
    #read in potential
    potential = lmp.Potential(input_dict['potential'], input_dict['potential_dir'])        
    
    #Run quick_a_Cij to refine values
    results_dict = quick_a_Cij(input_dict['lammps_command'], 
                               input_dict['initial_system'], 
                               potential, 
                               input_dict['symbols'], 
                               p_xx = input_dict['pressure_xx'], 
                               p_yy = input_dict['pressure_yy'], 
                               p_zz = input_dict['pressure_zz'],
                               delta = input_dict['strain_range'])
    
    #Save data model of results 
    results = data_model(input_dict, results_dict)
    with open('results.json', 'w') as f:
        results.json(fp=f, indent=4)

def input(*args):
    """Handles the input commands for this calculation."""
    
    #Read in input terms consistent across the atomman-based calculations
    input_dict = iprPy.tools.atomman_input.input(*args)
    
    #Read in input terms unique to this calculation
    input_dict['strain_range'] = float(input_dict.get('strain_range', 1e-5))
    input_dict['pressure_xx'] = iprPy.tools.atomman_input.value_unit(input_dict.get('pressure_xx', '0.0'), default_unit=input_dict['pressure_unit'])
    input_dict['pressure_yy'] = iprPy.tools.atomman_input.value_unit(input_dict.get('pressure_yy', '0.0'), default_unit=input_dict['pressure_unit'])
    input_dict['pressure_zz'] = iprPy.tools.atomman_input.value_unit(input_dict.get('pressure_zz', '0.0'), default_unit=input_dict['pressure_unit'])
    
    #Convert ucell box mult terms to single integers
    try: input_dict['a_mult'] = input_dict['a_mult'][1] - input_dict['a_mult'][0]
    except: pass
    try: input_dict['b_mult'] = input_dict['b_mult'][1] - input_dict['b_mult'][0]
    except: pass
    try: input_dict['c_mult'] = input_dict['c_mult'][1] - input_dict['c_mult'][0]
    except: pass
    
    return input_dict

def cij_script(template_file, system_info, pair_info, delta = 1e-5, steps = 2):
    """Create lammps script that strains a crystal in each direction x,y,z and shear yz,xz,xy independently."""    
    
    with open(template_file) as f:
        template = f.read()
    variable = {'atomman_system_info': system_info,
                'atomman_pair_info':   pair_info,
                'delta': delta, 
                'steps': steps}
    return '\n'.join(iprPy.tools.fill_template(template, variable, '<', '>'))
        
def quick_a_Cij(lammps_exe, cell, potential, symbols, p_xx=0.0, p_yy=0.0, p_zz=0.0, tol=1e-10, diverge_scale=3., delta = 1e-5):
    """
    Quickly refines static orthorhombic cell by evaluating the elastic constants and the virial pressure.
    
    Keyword Arguments:
    lammps_exe -- directory location for lammps executable
    system -- atomman.System to statically deform and evaluate a,b,c and Cij at a given pressure
    potential -- atomman.lammps.Potential representation of a LAMMPS implemented potential
    symbols -- list of element-model symbols for the Potential that correspond to the System's atypes
    pxx, pyy, pzz -- tensile pressures to equilibriate to.  Default is 0.0 for all.  
    tol -- the relative tolerance criterion for identifying box size convergence. Default is 1e-10.
    diverge_scale -- identifies a divergent system if x / diverge_scale < x < x * diverge_scale is not True for x = a,b,c.
    """
    
    #initial parameter setup
    converged = False                   #flag for if values have converged
    
    #define boxes for iterating
    cell_current = deepcopy(cell)       #cell with box parameters being evaluated
    cell_old = None                     #cell with previous box parameters evaluated
    
    for cycle in xrange(100):
        
        #Run LAMMPS and evaluate results based on cell_old
        results = calc_cij(lammps_exe, cell_current, potential, symbols, p_xx, p_yy, p_zz, delta)
        cell_new = results['cell_new']
        
        #Test if box has converged to a single size
        if np.allclose(cell_new.box.vects, cell_current.box.vects, rtol=tol):
            converged = True
            break
        
        #Test if box has converged to two sizes
        elif cell_old is not None and np.allclose(cell_new.box.vects, cell_old.box.vects, rtol=tol):
            #Run LAMMPS Cij script using average between alat0 and alat1
            box = am.Box(a = (cell_new.box.a + cell_old.box.a) / 2.,
                         b = (cell_new.box.b + cell_old.box.b) / 2.,
                         c = (cell_new.box.c + cell_old.box.c) / 2.)
            cell_current.box_set(vects=box.vects, scale=True)
            results = calc_cij(lammps_exe, cell_current, potential, symbols, p_xx, p_yy, p_zz, delta)                 
            
            converged = True
            break
        
        #Test if values have diverged from initial guess
        elif cell_new.box.a < cell.box.a / diverge_scale or cell_new.box.a > cell.box.a * diverge_scale:
            raise RuntimeError('Divergence of box dimensions')
        elif cell_new.box.b < cell.box.b / diverge_scale or cell_new.box.b > cell.box.b * diverge_scale:
            raise RuntimeError('Divergence of box dimensions')
        elif cell_new.box.c < cell.box.c / diverge_scale or cell_new.box.c > cell.box.c * diverge_scale:
            raise RuntimeError('Divergence of box dimensions')  
        elif results['ecoh'] == 0.0:
            raise RuntimeError('Divergence: cohesive energy is 0')
                
        #if not converged or diverged, update cell_old and cell_current
        else:
            cell_old, cell_current = cell_current, cell_new
    
    #Return values if converged
    if converged:        
        return results
    else:
        raise RuntimeError('Failed to converge after 100 cycles')

def calc_cij(lammps_exe, cell, potential, symbols, p_xx=0.0, p_yy=0.0, p_zz=0.0, delta=1e-5):
    """Runs cij_script and returns current Cij, stress, Ecoh, and new cell guess."""
    
    #setup system and pair info
    system_info = lmp.sys_gen(units =       potential.units,
                              atom_style =  potential.atom_style,
                              ucell =       cell,
                              size =        np.array([[0,3], [0,3], [0,3]]))

    pair_info = potential.pair_info(symbols)
    
    #create script and run
    with open('cij.in','w') as f:
        f.write(cij_script('cij.template', system_info, pair_info, delta=delta, steps=2))
    data = lmp.run(lammps_exe, 'cij.in')
    
    #get units for pressure and energy used by LAMMPS simulation
    lmp_units = lmp.style.unit(potential.units)
    p_unit = lmp_units['pressure']
    e_unit = lmp_units['energy']
    
    #Extract thermo values. Each term ranges i=0-12 where i=0 is undeformed
    #The remaining values are for -/+ strain pairs in the six unique directions
    lx = np.array(data.finds('Lx'))
    ly = np.array(data.finds('Ly'))
    lz = np.array(data.finds('Lz'))
    xy = np.array(data.finds('Xy'))
    xz = np.array(data.finds('Xz'))
    yz = np.array(data.finds('Yz'))
    
    pxx = uc.set_in_units(np.array(data.finds('Pxx')), p_unit)
    pyy = uc.set_in_units(np.array(data.finds('Pyy')), p_unit)
    pzz = uc.set_in_units(np.array(data.finds('Pzz')), p_unit)
    pxy = uc.set_in_units(np.array(data.finds('Pxy')), p_unit)
    pxz = uc.set_in_units(np.array(data.finds('Pxz')), p_unit)
    pyz = uc.set_in_units(np.array(data.finds('Pyz')), p_unit)
    
    pe = uc.set_in_units(np.array(data.finds('peatom')), e_unit)
    
    #Set the six non-zero strain values
    strains = np.array([ (lx[2] -  lx[1])  / lx[0],
                         (ly[4] -  ly[3])  / ly[0],
                         (lz[6] -  lz[5])  / lz[0],
                         (yz[8] -  yz[7])  / lz[0],
                         (xz[10] - xz[9])  / lz[0],
                         (xy[12] - xy[11]) / ly[0] ])

    #calculate cij using stress changes associated with each non-zero strain
    cij = np.empty((6,6))
    for i in xrange(6):
        delta_stress = np.array([ pxx[2*i+1]-pxx[2*i+2],
                                  pyy[2*i+1]-pyy[2*i+2],
                                  pzz[2*i+1]-pzz[2*i+2],
                                  pyz[2*i+1]-pyz[2*i+2],
                                  pxz[2*i+1]-pxz[2*i+2],
                                  pxy[2*i+1]-pxy[2*i+2] ])

        cij[i] = delta_stress / strains[i] 
        
    for i in xrange(6):
        for j in xrange(i):
            cij[i,j] = cij[j,i] = (cij[i,j] + cij[j,i]) / 2

    C = am.tools.ElasticConstants(Cij=cij)
    
    if np.allclose(C.Cij, 0.0):
        raise RuntimeError('Divergence of elastic constants to <= 0')
    try:
        S = C.Sij
    except:
        raise RuntimeError('singular C:\n'+str(C.Cij))

    
    #extract the current stress state
    stress = -1 * np.array([[pxx[0], pxy[0], pxz[0]],
                            [pxy[0], pyy[0], pyz[0]],
                            [pxz[0], pyz[0], pzz[0]]])
    
    s_xx = stress[0,0] + p_xx
    s_yy = stress[1,1] + p_yy
    s_zz = stress[2,2] + p_zz
    
    new_a = cell.box.a / (S[0,0]*s_xx + S[0,1]*s_yy + S[0,2]*s_zz + 1)
    new_b = cell.box.b / (S[1,0]*s_xx + S[1,1]*s_yy + S[1,2]*s_zz + 1)
    new_c = cell.box.c / (S[2,0]*s_xx + S[2,1]*s_yy + S[2,2]*s_zz + 1)
    
    if new_a <= 0 or new_b <= 0 or new_c <=0:
        raise RuntimeError('Divergence of box dimensions to <= 0')
    
    newbox = am.Box(a=new_a, b=new_b, c=new_c)
    cell_new = deepcopy(cell)
    cell_new.box_set(vects=newbox.vects, scale=True)
    
    return {'C':C, 'stress':stress, 'ecoh':pe[0], 'cell_new':cell_new}
    
def data_model(input_dict, results_dict=None):
    """Creates a DataModelDict containing the input and results data""" 
    
    #Create the root of the DataModelDict
    output = DM()
    output['calculation-system-relax'] = calc = DM()
    
    #Assign uuid
    calc['calculation'] = DM()
    calc['calculation']['id'] = input_dict['uuid']
    calc['calculation']['script'] = __calc_name__
    
    calc['calculation']['run-parameter'] = run_params = DM()
    run_params['strain-range'] = input_dict['strain_range']
    run_params['a-multiplyer'] = input_dict['a_mult']
    run_params['b-multiplyer'] = input_dict['b_mult']
    run_params['c-multiplyer'] = input_dict['c_mult']
    
    #Copy over potential data model info
    calc['potential'] = input_dict['potential']['LAMMPS-potential']['potential']
    
    #Save info on system file loaded
    system_load = input_dict['load'].split(' ')    
    calc['system-info'] = DM()
    calc['system-info']['artifact'] = DM()
    calc['system-info']['artifact']['file'] = os.path.basename(' '.join(system_load[1:]))
    calc['system-info']['artifact']['format'] = system_load[0]
    calc['system-info']['artifact']['family'] = input_dict['system_family']
    calc['system-info']['symbols'] = input_dict['symbols']
    
    #Save phase-state info
    calc['phase-state'] = DM()
    calc['phase-state']['temperature'] = DM([('value', 0.0), ('unit', 'K')])
    calc['phase-state']['pressure-xx'] = DM([('value', uc.get_in_units(input_dict['pressure_xx'],
                                                                       input_dict['pressure_unit'])), 
                                                       ('unit', input_dict['pressure_unit'])])
    calc['phase-state']['pressure-yy'] = DM([('value', uc.get_in_units(input_dict['pressure_yy'],
                                                                       input_dict['pressure_unit'])),
                                                       ('unit', input_dict['pressure_unit'])])
    calc['phase-state']['pressure-zz'] = DM([('value', uc.get_in_units(input_dict['pressure_zz'],
                                                                       input_dict['pressure_unit'])),
                                                       ('unit', input_dict['pressure_unit'])])                                                       
    
    #Save data model of the initial ucell
    calc['as-constructed-atomic-system'] = input_dict['ucell'].model(symbols = input_dict['symbols'], 
                                                                     box_unit = input_dict['length_unit'])['atomic-system']
    
    if results_dict is None:
        calc['status'] = 'not calculated'
    else:
        
        #Update ucell to relaxed lattice parameters
        relaxed_ucell = deepcopy(input_dict['ucell'])
        relaxed_ucell.box_set(a = results_dict['cell_new'].box.a / input_dict['a_mult'],
                              b = results_dict['cell_new'].box.b / input_dict['b_mult'],
                              c = results_dict['cell_new'].box.c / input_dict['c_mult'],
                              scale = True)
        
        #Save data model of the relaxed ucell                      
        calc['relaxed-atomic-system'] = relaxed_ucell.model(symbols = input_dict['symbols'], 
                                                            box_unit = input_dict['length_unit'])['atomic-system']
        
        #Save the final cohesive energy
        calc['cohesive-energy'] = DM([('value', uc.get_in_units(results_dict['ecoh'], 
                                                                           input_dict['energy_unit'])), 
                                                 ('unit', input_dict['energy_unit'])])
        
        #Save the final elastic constants
        c_family = calc['relaxed-atomic-system']['cell'].keys()[0]
        calc['elastic-constants'] = results_dict['C'].model(unit = input_dict['pressure_unit'], 
                                                            crystal_system = c_family)['elastic-constants']

    return output

 
    
if __name__ == '__main__':
    main(*sys.argv[1:])    

    
    
    
    
    
    
    
    
    