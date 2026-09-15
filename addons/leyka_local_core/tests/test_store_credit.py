from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestLeykaStoreCredit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.holder = cls.env["leyka.voucher.holder"].create(
            {"name": "Cliente prueba", "phone": "55 1234 5678"}
        )
        cls.credit = cls.env["leyka.store.credit"].create(
            {
                "holder_id": cls.holder.id,
                "amount_initial": 100.0,
            }
        )

    def test_partial_redemption_is_audited(self):
        self.credit.redeem(35.0, note="Prueba")
        self.assertEqual(self.credit.balance, 65.0)
        movement = self.credit.transaction_ids.sorted("id")[-1]
        self.assertEqual(movement.amount, -35.0)
        self.assertEqual(movement.balance_after, 65.0)

    def test_cannot_overdraw(self):
        with self.assertRaises(UserError):
            self.credit.redeem(101.0)
        self.assertEqual(self.credit.balance, 100.0)
