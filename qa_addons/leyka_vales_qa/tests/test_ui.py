from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged('post_install', '-at_install')
class TestValesUI(TestPointOfSaleHttpCommon):
    def test_issue_and_redeem_from_three_dots(self):
        program = self.env.ref('leyka_pos_vales.program_vales')
        self.env['loyalty.program'].search([('id', '!=', program.id)]).active = False
        program.write({'active': True, 'company_id': self.env.company.id})
        credit = self.env.ref('leyka_pos_vales.product_vale')
        credit.write({'active': True, 'available_in_pos': True})
        self.env['product.product'].create({
            'name': 'Pieza Leyka QA', 'list_price': 100, 'type': 'consu',
            'available_in_pos': True, 'taxes_id': [(5, 0, 0)],
        })
        self.env['product.product'].create({
            'name': 'Repuesto Leyka QA', 'list_price': 40, 'type': 'consu',
            'available_in_pos': True, 'taxes_id': [(5, 0, 0)],
        })
        self.main_pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('leyka_vales_issue_redeem', login='pos_user')
        card = self.env['loyalty.card'].search([('program_id', '=', program.id)])
        self.assertEqual(len(card), 1)
        self.assertEqual(card.points, 60)
        self.assertEqual(card.x_leyka_vale_phone, '2225238163')
        self.assertFalse(card.partner_id)
        self.assertFalse(card.expiration_date)
