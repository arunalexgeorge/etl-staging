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

from collections import defaultdict
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from cgitb import reset
from odoo.tools import float_is_zero, float_compare, float_round

class Aml(models.Model):
    _inherit = 'account.move.line'
    
    alt_uom_id = fields.Many2one('product.alt.uom', 'Package Name')
    alt_uom_qty = fields.Integer('Qty', default=1)