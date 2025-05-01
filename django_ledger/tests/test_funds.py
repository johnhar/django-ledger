import os

from django.test import override_settings
from django_ledger.tests.base import DjangoLedgerBaseTest

class FundFeatureTests(DjangoLedgerBaseTest):
    def test_fund_feature_enablement(self):
        """
        This requires the broader DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES setting to be True.
        """
        from importlib import reload
        from django.conf import settings
        from django_ledger import settings as dl_settings

        # first test that the fund feature is disabled by default
        self.assertTrue(hasattr(settings, 'DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES'))  # app's settings (i.e. dev_env in this case) grabs from OS
        self.assertEqual(settings.DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES,
                         os.getenv('DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES', 'False').lower() == 'true')
        self.assertTrue(hasattr(dl_settings, 'DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES'))    # django_ledger settings file has it defined
        self.assertFalse(dl_settings.DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES)               # and the default is False

        # now, override the settings file and reimport the django_ledger settings file
        with override_settings(DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES=True):
            reload(dl_settings)
            self.assertTrue(hasattr(settings, 'DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES'))   # app's settings now has the override setting
            self.assertTrue(hasattr(dl_settings, 'DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES'))    # django_ledger settings file is defined
            self.assertTrue(dl_settings.DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES)                # and it's overridden to True


@override_settings(DJANGO_LEDGER_ENABLE_NONPROFIT_FEATURES=True)
class FundModelTests(DjangoLedgerBaseTest):
    pass
