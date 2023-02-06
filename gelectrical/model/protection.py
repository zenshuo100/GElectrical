#  
#  Copyright 2019 Manu Varkey <manuvarkey@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
# 

import copy
import numpy as np
from shapely import Polygon, Point, LineString
# from scipy.interpolate import interp1d

# def interpolate(x,y):
#     fit_func = interp1d(np.log10(x), np.log10(y))
#     fit_func_mod = lambda x: list(10**(fit_func(np.log10(np.array(x)))))
#     return fit_func_mod

# local files import
from .. import misc
from ..misc import FieldDict


class ProtectionModel():
    """Generic protection base element"""

    def __init__(self, title, parameters, curve_u, curve_l, element_type='protection'):
        """
            data_struct: Protection datastructure of following format
            
            { 
                'type': 'protection' | 'damage'
                'parameters': { 'var_1': [caption, unit, value, value_list], 
                                'var_2': [caption, unit, value, value_list] ... },
                'data': {'curve_u': [('point', i1, t1), 
                                ('iec', tms, i_n, k, c, alpha, i1, i2, n), 
                                ('iec_inverse', tms, i_n, i1, i2, n), 
                                ('iec_v_inverse', tms, i_n, i1, i2, n), 
                                ('iec_e_inverse', tms, i_n, i1, i2, n), 
                                ('ieee_m_inverse', tms, i_n, i1, i2, n), 
                                ('ieee_v_inverse', tms, i_n, i1, i2, n), 
                                ('ieee_e_inverse', tms, i_n, i1, i2, n), 
                                ('thermal', tms, i_n, i1, i2, n),
                                    ... ],
                        'curve_l': ...}
                'graph_model'      : (title, models)}
            }
        """
        self.title = title
        self.data_struct = {'type'          : element_type,
                            'parameters'    : parameters,
                            'data'          : {'curve_u': curve_u,'curve_l': curve_l},
                            'graph_model'   : []}
        # Generated variables
        self.curve_upper = None  # Upper t vs I protection curve as list of tuples
        self.curve_lower = None  # Lower t vs I protection curve as list of tuples
        self.polygon = None
        self.linestring_upper = None
        self.linestring_lower = None

    @classmethod
    def new_from_data(cls, data_struct):
        if data_struct['type'] == 'protection':
            title = data_struct['graph_model'][0]
            parameters = data_struct['parameters']
            curve_u = data_struct['data']['curve_u']
            curve_l = data_struct['data']['curve_l']
            return cls(title, parameters, curve_u, curve_l)
        else:
            raise ValueError('Wrong data structure passed')

    def get_data_fields(self, modify_code=''):
        fields = dict()
        for key, (caption, unit, value, selection_list) in self.data_struct['parameters'].items():
            fields[modify_code+key] = misc.get_field_dict('float', caption, unit, value, 
                                                            selection_list=selection_list, 
                                                            status_inactivate=False)
        return fields

    def update_graph(self):
        if self.data_struct['type'] == 'protection':
            polygon_pnts = np.array((self.polygon.exterior.coords))
            xval = list(polygon_pnts[:,0])
            yval = list(polygon_pnts[:,1])
            graph_model = [self.title, [{'mode':misc.GRAPH_DATATYPE_POLYGON, 
                                            'title':self.title, 
                                            'xval':xval, 
                                            'yval': yval},]]
            self.data_struct['graph_model'] = graph_model
        elif self.data_struct['type'] == 'damage':
            xval1 = [x for x,y in self.curve_upper]
            yval1 = [y for x,y in self.curve_upper]
            xval2 = [x for x,y in self.curve_lower]
            yval2 = [y for x,y in self.curve_lower]
            graphs = []
            damage_flag = False
            starting_flag = False

            if xval1 and yval1:
                graphs.append({'mode':misc.GRAPH_DATATYPE_PROFILE, 
                                            'title': self.title + ' - Damage', 
                                            'xval':xval1, 
                                            'yval': yval1})
                damage_flag = True
            if xval2 and yval2:
                graphs.append({'mode':misc.GRAPH_DATATYPE_PROFILE, 
                                            'title':self.title + ' - Starting', 
                                            'xval':xval2, 
                                            'yval': yval2})
                starting_flag = True

            if damage_flag and not starting_flag:
                title = self.title + ' - Damage curve'
            elif starting_flag and not damage_flag:
                title = self.title + ' - Starting curve'
            else:
                title = self.title

            graph_model = [title, graphs]
            self.data_struct['graph_model'] = graph_model
            

    def update_parameters(self, parameters):
        for key, field in parameters.items():
            if key in self.data_struct['parameters']:
                self.data_struct['parameters'][key][2] = field[2]

    def evaluate_curves(self, fields, data_fields=None):
        
        # Variables for evaluation
        f = FieldDict(fields)
        if data_fields:
            d = FieldDict(data_fields)
        else:
            d = FieldDict(self.get_data_fields())
        
        # Functions for curve evaluation
        def point(i1, t1):
            return (i1,), (t1,)

        def iec(tms, i_n, k, c, alpha, i1, i2, t_min, n):
            if i2 > i1:
                i_array = np.geomspace(i1,i2,num=n)
                t_array_1 = tms*(k/((i_array/i_n)**alpha - 1) + c)
                t_array_2 = np.ones(i_array.shape)*t_min
                t_array = np.maximum(t_array_1, t_array_2)
                return list(i_array), list(t_array)
            else:
                return [], []

        def thermal(tms, i_n, i1, i2, n):
            # As per IEC 60255-8
            i_array = np.geomspace(i1,i2,num=n)
            t_array = tms*np.log(i_array**2/(i_array**2 - i_n**2))
            return list(i_array), list(t_array)

        def i2t(tms, i_n, k, alpha, i1, i2, t_min, n):
            if i2 > i1:
                i_array = np.geomspace(i1,i2,num=n)
                t_array_1 = tms*(k/((i_array/i_n)**alpha))
                t_array_2 = np.ones(i_array.shape)*t_min
                t_array = np.maximum(t_array_1, t_array_2)
                return list(i_array), list(t_array)
            else:
                return [], []

        iec_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 0.14, 0, 0.02, i1, i2, t_min, n) # As per IEC 60255-3
        iec_v_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 13.5, 0, 1, i1, i2, t_min, n) # As per IEC 60255-3
        iec_e_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 80, 0, 2, i1, i2, t_min, n) # As per IEC 60255-3
        ieee_m_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 0.0515, 0.1140, 0.02, i1, i2, t_min, n)
        ieee_v_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 19.61, 0.491, 2, i1, i2, t_min, n)
        ieee_e_inverse = lambda tms, i_n, i1, i2, t_min, n: iec(tms, i_n, 28.2, 0.1217, 2, i1, i2, t_min, n)
        
        def eval_curve(curve):
            var_dict = {'f': f, 'd': d}
            func_dict = {   'point'         : point,
                            'iec'           : iec,
                            'iec_inverse'   : iec_inverse,
                            'iec_v_inverse' : iec_v_inverse,
                            'iec_e_inverse' : iec_e_inverse,
                            'ieee_m_inverse': ieee_m_inverse,
                            'ieee_v_inverse': ieee_v_inverse,
                            'ieee_e_inverse': ieee_e_inverse,
                            'thermal'       : thermal,
                            'i2t'           : i2t
                        }
            # Evaluate curve
            curve_i = []
            curve_t = []
            for func_str, *data in curve:
                func = eval(func_str, func_dict)
                data_eval = [x if isinstance(x, (int, float)) else eval(x, var_dict) for x in data]
                i_array, t_array = func(*data_eval)
                curve_i += i_array
                curve_t += t_array
            
            curve = [(x,y) for x,y in zip(curve_i, curve_t)]

            # fit_func = interpolate(curve_i, curve_t)
            # X = np.geomspace(min(curve_i), max(curve_i), num=50)
            # Y = fit_func(X)
            # curve = [(x,y) for x,y in zip(X, Y)]

            return curve

        # Evaluate curves
        self.curve_upper = eval_curve(self.data_struct['data']['curve_u'])
        self.curve_lower = eval_curve(self.data_struct['data']['curve_l'])

        # Geometry elements
        self.linestring_upper = LineString(reversed(self.curve_upper))
        self.linestring_lower = LineString(self.curve_lower)
        self.polygon = Polygon(list(reversed(self.curve_upper)) + self.curve_lower)

    def get_evaluated_model(self, fields, data_fields=None):
        self.evaluate_curves(fields, data_fields)  # Evaluate curves
        self.update_graph()  # Update graph
        return copy.deepcopy(self.data_struct)

