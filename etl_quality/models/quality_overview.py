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


class QCOverview(models.Model):
    _name = 'qc.overview'
    _description = 'QC Overview'

    name = fields.Char("Name", required=True)
    type = fields.Selection([('grn', 'GRN'), ('mo', 'MO')], required=True)

    pending_count = fields.Integer("Pending Count", compute="_compute_pending_count" )
    ongoing_count = fields.Integer("Ongoing Count", compute="_compute_ongoing_count")
    completed_count = fields.Integer("Completed Count", compute="_compute_completed_count" )

    def _compute_pending_count(self):
        for qc in self:
            if qc.type == 'grn':
                qc.pending_count = self.env['grn.qc'].search_count([('state', '=', 'pending')])
            else:
                qc.pending_count = self.env['mo.qc'].search_count([('state', '=', 'pending')])

    def _compute_ongoing_count(self):
        for qc in self:
            if qc.type == 'grn':
                qc.ongoing_count = self.env['grn.qc'].search_count([('state', '=', 'ongoing')])
            else:
                qc.ongoing_count = self.env['mo.qc'].search_count([('state', '=', 'ongoing')])

    def _compute_completed_count(self):
        for qc in self:
            if qc.type == 'grn':
                qc.completed_count = self.env['grn.qc'].search_count([('state', '=', 'completed')])
            else:
                qc.completed_count = self.env['mo.qc'].search_count([('state', '=', 'completed')])

    def action_open_pending(self):
        if self.type == 'grn':
            action = self.env.ref('etl_quality.action_grn_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'pending')]
        else:
            action = self.env.ref('etl_quality.action_mo_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'pending')]
        return action

    def action_open_ongoing(self):
        if self.type == 'grn':
            action = self.env.ref('etl_quality.action_grn_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'ongoing')]
        else:
            action = self.env.ref('etl_quality.action_mo_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'ongoing')]
        return action

    def action_open_completed(self):
        if self.type == 'grn':
            action = self.env.ref('etl_quality.action_grn_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'completed')]
        else:
            action = self.env.ref('etl_quality.action_mo_qcs').sudo().read()[0]
            action['domain'] = [('state', '=', 'completed')]
        return action
