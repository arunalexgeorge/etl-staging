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


class StockLocation(models.Model):
    _inherit = 'stock.location'

    branch_id = fields.Many2one('res.branch')
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            args += ['|', ('branch_id', 'in', branches_ids), ('branch_id', '=', False)]
        return super(StockLocation, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'allowed_branch_ids' in self._context:
            branches_ids = self._context['allowed_branch_ids']
        else:
            branches_ids = self.env.user.branch_ids.ids
        domain += ['|', ('branch_id', 'in', branches_ids), ('branch_id', '=', False)]
        return super(StockLocation, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

    # @api.constrains('branch_id')
    # def _check_branch(self):
    #     warehouse_obj = self.env['stock.warehouse']
    #     warehouse_id = warehouse_obj.search(
    #         ['|', '|', ('wh_input_stock_loc_id', '=', self.id),
    #          ('lot_stock_id', '=', self.id),
    #          ('wh_output_stock_loc_id', '=', self.id)])
    #     for warehouse in warehouse_id:
    #         if self.branch_id != warehouse.branch_id:
    #             raise UserError(_('Configuration error\nYou  must select same branch on a location as assigned on a warehouse configuration.'))
    #
    # @api.onchange('branch_id')
    # def _onchange_branch_id(self):
    #     selected_brach = self.branch_id
    #     if selected_brach:
    #         user_id = self.env['res.users'].browse(self.env.uid)
    #         user_branch = user_id.sudo().branch_id
    #         if not self.env.user.has_group('base.group_user') or (user_branch and user_branch.id != selected_brach.id):
    #             raise UserError("Please select active branch only. Other may create the Multi branch issue. \n\ne.g: If you wish to add other branch then Switch branch from the header and set that.")

