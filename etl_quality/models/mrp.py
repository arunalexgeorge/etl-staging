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
    
class MRP(models.Model):
    _inherit = 'mrp.production'
    
    def action_open_qcs(self):
        if self.qc_status == 'completed':
            return True
        product = self.product_id
        params = self.env['mo.parameter'].search([('product_id', '=', product.id)])
        if not params:
            raise UserError('Please create MO Parameters for %s!'%(product.name))
        for param in params:
            if not param.line_ids:
                raise UserError('Please create MO Parameters for %s!'%(product.name))
        if not self.qc_id:
            qc_id = self.env['mo.qc'].create({
                'production_id': self.id,
                'product_id': product.id
                }).id
            self.qc_id = qc_id
            for param in params:
                for line in param.line_ids:
                    self.env['mo.qc.line'].create({
                        'qc_id': qc_id,
                        'name': line.name,
                        'specification': line.specification
                        })
        if self.qc_id and not self.qc_id.line_ids:
            for param in params:
                for line in param.line_ids:
                    self.env['mo.qc.line'].create({
                        'qc_id': self.qc_id.id,
                        'name': line.name,
                        'specification': line.specification
                        })
    
    @api.depends('qc_id', 'qc_id.state')
    def _compute_qc_status(self):
        for mrp in self:
            if mrp.qc_id:
                mrp.qc_status = mrp.qc_id.state

    qc_id = fields.Many2one('mo.qc', 'MO QC', copy=False)
    qc_status = fields.Selection([
        ('pending', 'Pending'), ('ongoing', 'Ongoing'), ('completed', 'Completed')
        ], 'QC Status', compute='_compute_qc_status', store=True)
