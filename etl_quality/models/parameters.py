# -*- coding: utf-8 -*-
#############################################################################
#
#    Steigend IT Solutions.
#
#    Copyright (C) 2023-TODAY Steigend IT Solutions.
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_datetime
    
class GrnParameters(models.Model):
    _name = 'grn.parameter'
    _description = 'GRN Parameters'
    
    @api.depends('product_id', 'product_id.name')
    def _compute_name(self):
        for param in self:
            if param.product_id:
                param.name = param.product_id.name
            else:
                param.name = ''
            
    name = fields.Char('Name', compute='_compute_name', store=True)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    line_ids = fields.One2many('grn.parameter.line', 'parameter_id', 'Quality Parameters')
    active = fields.Boolean(default=True)

class GrnParameterLines(models.Model):
    _name = 'grn.parameter.line'
    _description = 'GRN Parameter Lines'
    
    name = fields.Char('Parameter Name', required=True)
    specification = fields.Char('Specification')
    parameter_id = fields.Many2one('grn.parameter', 'GRN Parameter')

class MOParameters(models.Model):
    _name = 'mo.parameter'
    _description = 'MO Parameters'
    
    @api.depends('product_id', 'product_id.name')
    def _compute_name(self):
        for param in self:
            if param.product_id:
                param.name = param.product_id.name
            else:
                param.name = ''
            
    name = fields.Char('Name', compute='_compute_name', store=True)
    categ_id = fields.Many2one('product.category', 'Product Category', required=False)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    line_ids = fields.One2many('mo.parameter.line', 'parameter_id', 'Quality Parameters')

class MOParameterLines(models.Model):
    _name = 'mo.parameter.line'
    _description = 'MO Parameter Lines'
    
    name = fields.Char('Parameter Name', required=True)
    specification = fields.Char('Specification')
    parameter_id = fields.Many2one('mo.parameter', 'MO Parameter')
    
    