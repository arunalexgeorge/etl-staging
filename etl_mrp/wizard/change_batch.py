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

class ChangeProductionQty(models.TransientModel):
    _inherit = "change.production.qty"

    def change_prod_qty(self):
        super(ChangeProductionQty, self).change_prod_qty()
        self.mo_id.action_assign()
                
class ChangeBatchQty(models.TransientModel):
    _name = 'change.batch.qty'
    _description = 'Change Batch Qty'

    mo_id = fields.Many2one('mrp.production', 'Manufacturing Order', required=True, ondelete='cascade')
    batch_qty = fields.Integer('Batch Quantity', required=True)
    
    @api.model
    def default_get(self, fields):
        res = super(ChangeBatchQty, self).default_get(fields)
        if 'mo_id' in fields and not res.get('mo_id') and self._context.get('active_model') == 'mrp.production' and self._context.get('active_id'):
            res['mo_id'] = self._context['active_id']
        if 'batch_qty' in fields and not res.get('batch_qty') and res.get('mo_id'):
            res['batch_qty'] = self.env['mrp.production'].browse(res['mo_id']).batch_qty
        return res
    
    def change_batch_qty(self):
        self.mo_id.write({
            'batch_qty': self.batch_qty, 
            'product_qty': self.batch_qty * self.mo_id.bom_id.product_qty
            })
        for move in self.mo_id.move_raw_ids:
            move.write({'product_uom_qty': self.batch_qty * move.bom_qty})
        return {}
    