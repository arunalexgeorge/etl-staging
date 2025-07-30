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

from odoo import api, fields, models, _
from odoo.osv import expression
import pytz
from datetime import datetime

class Branch(models.Model):
    _name = 'res.branch'
    _description = 'Branch'
    # _order = 'name'

    name = fields.Char('Branch Name', required=True)
    code = fields.Char('Branch Code', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company.id)
    telephone = fields.Char(string='Telephone No')
    address = fields.Text('Branch Address')
    partner_id = fields.Many2one('res.partner', 'Partner')
    branch_location_ids = fields.One2many('branch.location', 'branch_id', 'Transit Locations')
    
    @api.onchange('partner_id')
    def onchange_partner(self):
        address = ''
        if self.partner_id:
            if self.partner_id.street:
                address += self.partner_id.street + ','
            if self.partner_id.street2:
                address += self.partner_id.street2 + ','
            if self.partner_id.city:
                address += self.partner_id.city + '-' + self.partner_id.zip or ''
        self.address = address
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'current_branch' in self._context:
                branch_ids = [self.env.user.branch_id.id]
            elif 'allowed_branch_ids' in self._context:
                branch_ids = self._context['allowed_branch_ids']
            else:
                branch_ids = self.env.user.branch_ids.ids
            args += [('id', 'in', branch_ids)]
        return super(Branch, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if 'show_all' in self._context or 'no_filter' in self._context:
            branches_ids = self.search([]).ids
            args += [('id', 'in', branches_ids)]
        else:
            if 'current_branch' in self._context:
                branches_ids = [self.env.user.branch_id.id]
            else:
                branches_ids = self.env.user.branch_ids.ids
                args += [('id', 'in', branches_ids)]
        
        return super(Branch, self)._name_search(name=name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid)

class BranchLocation(models.Model):
    _name = 'branch.location'
    _description = 'Branch Location'
    
    branch_id = fields.Many2one('res.branch', 'Branch(O2M)')
    location_id = fields.Many2one('stock.location', 'Transit Location')
    inter_branch_id = fields.Many2one('res.branch', 'Branch')
