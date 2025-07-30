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
from odoo.tools.float_utils import float_compare, float_is_zero


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    @api.model
    def _get_inventory_fields_create(self):
        res = super(StockQuant, self)._get_inventory_fields_create()
        res.append('branch_id')
        res.append('reserved_quantity')
        return res
    
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
            args += ['|',('branch_id', '=', False), ('branch_id', 'in', branches_ids)]
            location_ids = self.env['stock.location'].search([('branch_id', 'in', branches_ids)]).ids
            args += [('location_id', 'in', location_ids)]
        return super(StockQuant, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            domain += ['|',('branch_id', '=', False), ('branch_id', 'in', branches_ids)]
            location_ids = self.env['stock.location'].search([('branch_id', 'in', branches_ids)]).ids
            domain += [('location_id', 'in', location_ids)]
        return super(StockQuant, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.model
    def default_get(self, default_fields):
        res = super(StockQuant, self).default_get(default_fields)
        if self._context.get('branch'):
            branch_id = self._context.get('branch')
        else:
            branch_id = self.env.user.branch_id.id
        warehouse = self.env['stock.warehouse'].with_context(no_filter=True).search([('branch_id','=', branch_id)])[0]
        res.update({
            'branch_id' : branch_id,
            'location_id': warehouse.lot_stock_id.id
            })
        return res

    branch_id = fields.Many2one('res.branch', "Branch")

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None, in_date=None):
        self = self.sudo()
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
        if lot_id and quantity > 0:
            quants = quants.filtered(lambda q: q.lot_id)

        if location_id.should_bypass_reservation():
            incoming_dates = []
        else:
            incoming_dates = [quant.in_date for quant in quants if quant.in_date and
                              float_compare(quant.quantity, 0, precision_rounding=quant.product_uom_id.rounding) > 0]
        if in_date:
            incoming_dates += [in_date]
        # If multiple incoming dates are available for a given lot_id/package_id/owner_id, we
        # consider only the oldest one as being relevant.
        if incoming_dates:
            in_date = min(incoming_dates)
        else:
            in_date = fields.Datetime.now()

        quant = None
        if quants:
            # see _acquire_one_job for explanations
            self._cr.execute("SELECT id FROM stock_quant WHERE id IN %s ORDER BY lot_id LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED", [tuple(quants.ids)])
            stock_quant_result = self._cr.fetchone()
            if stock_quant_result:
                quant = self.browse(stock_quant_result[0])

        if quant:
            quant.write({
                'quantity': quant.quantity + quantity,
                'in_date': in_date,
            })                
        else:
            if self._context.get('branch'):
                self.create({
                    'product_id': product_id.id,
                    'location_id': location_id.id,
                    'quantity': quantity,
                    'lot_id': lot_id and lot_id.id,
                    'package_id': package_id and package_id.id,
                    'owner_id': owner_id and owner_id.id,
                    'in_date': in_date,
                    'branch_id': self._context.get('branch')
                })
            else:
                self.create({
                    'product_id': product_id.id,
                    'location_id': location_id.id,
                    'quantity': quantity,
                    'lot_id': lot_id and lot_id.id,
                    'package_id': package_id and package_id.id,
                    'owner_id': owner_id and owner_id.id,
                    'in_date': in_date,
                    'branch_id': self.env.user.branch_id.id
                })                
        return self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=False, allow_negative=True), in_date
