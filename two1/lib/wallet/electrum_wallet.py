from subprocess import check_output
import subprocess
import json

from two1.lib.wallet.base_wallet import BaseWallet, satoshi_to_btc
import os


class ElectrumWallet(BaseWallet):
    """ A simplified interface to the python wallet.
    """

    def __init__(self, TWO1_PATH=None):
        super(ElectrumWallet, self).__init__()
        # check if electrum is works
        # will throw an OSError if electrum does not work
        # output = check_output(["electrum","--help"]).decode("utf-8")
        # start daemon

    def start_daemon(self):
        try:
            check_output(["electrum", "daemon", "start"])
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                # raise if returncode is not 1.
                # This is a the case when there was trouble in
                # starting the daemon
                return False
        return True

    def addresses(self):
        """ Gets the address list for the current wallet.

        Returns:
            (list): The current list of addresses in this wallet.
        """
        normalized = []
        resp = self._electrum_call_with_simple_error(['listaddresses'],
                                                     'Failed to get addresses')

        # Validate Response
        self._type_check('Response', resp, list)
        for item in resp:
            self._type_check('address', item, str)
            normalized.append(str(item))

        # Return normalized
        return normalized

    def current_address(self):
        """ Gets the preferred address.

        Returns:
            (str): The current preferred payment address.
        """
        return self.addresses()[len(self.addresses()) - 1]

    def confirmed_balance(self):
        """ Gets the current confirmed balance of the wallet.

        Returns:
            (number): The current confirmed balance.
        """
        resp = self._electrum_call_with_simple_error(['getbalance'],
                                                     'Failed to get balance')
        self._type_check('Response', resp, object)
        balance = 0
        if 'confirmed' in resp:
            self._type_check('confirmed', resp['confirmed'], str)
            balance = int(float(resp['confirmed']) * satoshi_to_btc)

        return balance

    def unconfirmed_balance(self):
        """ Gets the current unconfirmed balance of the wallet.

        Returns:
            (number): The current unconfirmed balance.
        """
        resp = self._electrum_call_with_simple_error(['getbalance'],
                                                     'Failed to get balance')
        self._type_check('Response', resp, object)
        balance = 0
        if 'unconfirmed' in resp:
            self._type_check('unconfirmed', resp['unconfirmed'], str)
            balance = int(float(resp['unconfirmed']) * satoshi_to_btc)

        return balance

    def sign_transaction(self, tx):
        """ Signs the inputted transaction.

        Returns:
            (tx): The signed transaction object.
        """
        return self._normalize_tx_resp(
            self._electrum_call_with_simple_error(['signtransaction', tx],
                                                  'Failed to sign transaction.'))['hex']

    def broadcast_transaction(self, tx):
        """ Broadcasts the transaction to the Bitcoin network.

        Args:
            tx (tx): The transaction to be broadcasted to the Bitcoin network..

        Returns:
            (str): The name of the transaction that was broadcasted.
        """
        return str(self._electrum_call_with_simple_error(['broadcast', tx],
                                                         'Failed to broadcasts transaction.'))

    def make_signed_transaction_for(self, address, amount):
        """ Makes a raw signed unbrodcasted transaction for the specified amount.

        Args:
            address (str): The address to send the Bitcoin to.
            amount (number): The amount of Bitcoin to send.

        Returns:
            (dictionary): A dictionary containing the transaction name
                and the raw transaction object.
        """
        self._type_check('address', address, str)
        self._type_check('amount', amount, int)
        return self._normalize_tx_resp(
            self._electrum_call_with_simple_error(['payto',
                                                   str(address),
                                                   str(amount / satoshi_to_btc)],
                                                  'Failed to make transaction'))['hex']

    def send_to(self, address, amount):
        """ Sends Bitcoin to the provided address for the specified amount.

        Args:
            address (str): The address to send the Bitcoin to.
            amount (number): The amount of Bitcoin to send.

        Returns:
            (dictionary): A dictionary containing the transaction name
                and the raw transaction object.
        """
        signed = self.make_raw_signed_transaction(address, amount)
        return self.broadcast_raw_transaction(signed)

    @property
    def is_configured(self):
        """ Returns the configuration/initialization status of the
            wallet.

        Returns:
            (bool): Returns True if the wallet has been configured and
                ready to use otherwise False
        """
        # create wallet config file if not present
        config_file = self._electrum_data_path("config")
        if not os.path.isfile(config_file):
            self._electrum_create_default_config(config_file)

        # Check for wallet file
        return os.path.isfile(self._electrum_data_path("wallets",
                                                       "default_wallet"))

    @property
    def config_options(self):
        """ Returns the configuration options available for the
            wallet.

        Returns:
            (dict): The keys of this dictionary are the available
            configuration settings/options for the wallet. The value
            for each key represents the possible values for each
            option.  e.g. {key_style: ["HD","Brain","Simple"], ....}
        """
        return {
            "key_style": ["HD", "Brain", "Simple", "Multi_Signiture"],
            # "version": self._electrum_call_with_simple_error(['version', 'Failed to get version'], "I fail")
        }

    def configure(self, config_options):
        """ Automatically configures the wallet with the provided configuration options
        """
        self._electrum_call_with_nonjson(['create'],
                                         "Could not create wallet.")

    @staticmethod
    def _type_check(name, var, typeN):
        """ Type check validation utility.

        Args:
            name (string): The name of the variable to put in the
                error message.
            var (*): The value to type check.
            typeN (type): The type to validate the value with.
        """
        if isinstance(var, typeN):
            return
        raise ValueError('%s was of an unexpected type (got \"%s\" expected \"%s\")' %
                         (name, str(var.__clas__), str(typeN)))

    @staticmethod
    def _normalize_tx_resp(resp):
        """ Normalizes the inputted transaction response.

        Args:
            resp:

        Returns:
            (list): List of address in the wallet.
        """
        if not all(name in ['hex', 'complete'] for name in resp):
            raise ValueError('Missing expected value in CLI response.')

        return {
            'hex': str(resp['hex']),
            'complete': bool(resp['complete'])
        }

    @staticmethod
    def _call_electrum(args):
        """ Calls and retrieves the parsed output of the electrum CLI
            wallet using the provided arguments.

        Args:
            args (list): list of arguments to call on electrum.

        Returns:
            (*): The parsed foundation object.
        """
        _args = ['electrum']

        # Add arguments
        for item in args:
            _args.append(item)

        # Call and get output
        output = check_output(_args).decode("utf-8")

        # Try to decode output
        try:
            resp = json.loads(output)
        except Exception as e:
            # Add the payload to the error.
            print(output)
            e.payload = output
            raise e

        # Return Output
        return resp

    @staticmethod
    def _electrum_call_with_simple_error(args, errMsg):
        """ Calls the electrum CLI and substitutes any errors with the given message.

        Args:
            args (list): list of arguments to call on electrum.
            errMsg (str): The message to replace caught messages.

        Returns:
            (*): The parsed foundation object.
        """
        try:
            return ElectrumWallet._call_electrum(args)
        except Exception:
            raise ValueError(errMsg)

    @staticmethod
    def _electrum_call_with_nonjson(args, errMsg):
        """ Calls the electrum CLI where the expected output from Electrum is non-json.

        Args:
            args (list): list of arguments to call on electrum.
            errMsg (str): The message to replace caught messages.

        Returns:
            (*): The parsed foundation object.
        """
        try:
            _args = ['electrum']

            for item in args:
                _args.append(item)
            subprocess.call(_args)
        except Exception:
            raise ValueError(errMsg)

    @staticmethod
    def _electrum_data_path(*args):
        return os.path.join(os.path.expanduser("~"), ".electrum", *args)

    @staticmethod
    def _electrum_create_default_config(config_file):
        with open(config_file, mode="w") as fh:
            fh.write('''
                {
                    "auto_connect": true,
                    "console-history": [],
                    "gui_show_history": false,
                    "gui_show_receiving": false,
                    "is_maximized": false,
                    "lite_mode": false,
                    "winpos-qt": [
                    173,
                    117,
                    840,
                    429
                    ]
                }
                ''')