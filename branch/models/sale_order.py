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
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def default_get(self,fields):
        res = super(SaleOrder, self).default_get(fields)
        branch_id = warehouse_id = False
        if self.env.user.branch_id:
            branch_id = self.env.user.branch_id.id
        if branch_id:
            branched_warehouse = self.env['stock.warehouse'].search([('branch_id','=',branch_id)])
            if branched_warehouse:
                warehouse_id = branched_warehouse.ids[0]
        
        if not warehouse_id:
            warehouse_id = self.env.user._get_default_warehouse_id()
            warehouse_id = warehouse_id.id

        res.update({
            'branch_id' : branch_id,
            'warehouse_id' : warehouse_id
            })

        return res

    branch_id = fields.Many2one('res.branch', string="Branch")
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        user = self.env.user
        if 'no_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(SaleOrder, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        user = self.env.user
        if 'no_filter' in self._context:
            pass
        else:
            branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
            domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
        return super(SaleOrder, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res['branch_id'] = self.branch_id.id
        return res


    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        selected_brach = self.branch_id
        if selected_brach:
            user_id = self.env['res.users'].browse(self.env.uid)
            user_branch = user_id.sudo().branch_id
            if user_branch and user_branch.id != selected_brach.id:
                raise UserError("Please select active branch only. Other may create the Multi branch issue. \n\ne.g: If you wish to add other branch then Switch branch from the header and set that.")

