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


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'


    def _create_invoice(self, order, so_line, amount):
        result = super(SaleAdvancePaymentInv, self)._create_invoice(order, so_line, amount)

        branch_id = False

        if order.branch_id:
            branch_id = order.branch_id.id
        elif self.env.user.branch_id:
            branch_id = self.env.user.branch_id.id

        result.write({
            'branch_id' : branch_id
            })

        return result

class AccountPaymentRegisterInv(models.TransientModel):
    _inherit = 'account.payment.register'

    branch_id = fields.Many2one('res.branch')

