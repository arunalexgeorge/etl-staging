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

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo.tools.misc import clean_context, OrderedSet, groupby
import logging
from asyncio.base_events import ssl
logger = logging.getLogger(__name__)
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime
from odoo.tools import pycompat

class StatementImport(models.TransientModel):
    _name = 'statement.import'
    _description = 'Statement Import' 

    journal_id = fields.Many2one('account.journal', 'Bank')
    date = fields.Date('As On Date')
    data_file = fields.Binary('CSV File')
    data_file_name = fields.Char('File Name')
    branch_id = fields.Many2one('res.branch', 'Branch')
    
    @api.model
    def default_get(self, default_fields):
        res = super(StatementImport, self).default_get(default_fields)
        branch_id = self.env.user.branch_id.id
        if branch_id != self.env.user.company_id.ho_branch_id.id:
            raise UserError('Switch to HO Branch for statement Upload')
        res.update({
            'journal_id' : self._context.get('active_id'),
            'branch_id': branch_id
            })
        return res
    
    def action_import(self):
        file_data = pycompat.csv_reader(BytesIO(base64.decodebytes(self.data_file)), quotechar='"', delimiter=',')
        count = 0
        for data in file_data:
            count += 1
            if count == 2:
                starting_balance = round(float(data[0]), 2)
                ending_balance = round(float(data[1]), 2)
                narration = data[2]
            if count > 2:
                break
        
        bs_obj = self.env['account.bank.statement']
        bs_line_obj = self.env['account.bank.statement.line']
        banks_statements = bs_obj.search([('journal_id', '=', self.journal_id.id)], order='date desc, id desc')
        if banks_statements:
            bs = banks_statements[0]
            if round(bs.balance_end, 2) != starting_balance:
                raise UserError('Starting Balance should match with Previous Statement Ending Balance')
        bs = bs_obj.create({
            'journal_id': self.journal_id.id,
            'balance_start': starting_balance,
            'balance_end': ending_balance,
            'balance_end_real': ending_balance,
            'company_id': 1,
            'date': self.date,
            'name': narration
            })
        for data in file_data:
            bs_line_obj.create({
                'journal_id': self.journal_id.id,
                'amount': float(str(data[2]).replace(',', '')),
                'statement_id': bs.id,
                'company_id': 1,
                'date': datetime.strptime(data[0], "%d-%m-%Y").strftime('%Y-%m-%d'),
                'payment_ref': data[1]
                })
        return {'type': 'ir.actions.act_window_close'} 
    