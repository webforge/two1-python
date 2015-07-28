from two1.bitcoin.utils import *
from two1.bitcoin.script import Script
from two1.bitcoin.txn import CoinbaseInput, TransactionInput, TransactionOutput, Transaction


class BitshareCoinbaseTransaction(Transaction):
    """ This class is identical to Transaction except provides an additional
        method to serialize specifically for the client, meaning it removes
        the last output (assumes the last one is the Bitshare output) and the
        locktime, before returning the raw bytes.

    Args:
        version (int): Transaction version (should always be 1). Endianness: host
        inputs (list(TransactionInput)): all the inputs that spend bitcoin.
        outputs (list(TransactionOutput)): all the outputs to which bitcoin is sent.
           *This should include the Bitshare-added output.*
        lock_time (int): Time or a block number. Endianness: host
    """

    def __init__(self, version, inputs, outputs, lock_time):
        super().__init__(version, inputs, outputs, lock_time)
        self.bitshare_output_length = len(bytes(outputs[-1]))

    def client_serialize(self):
        """ Serializes the coinbase transaction without the Bitshare-added output
            or the lock-time. This is useful specifically for creating work for 21
            Bitshare chips.

        Returns:
            b (bytes): serialized byte stream, without the last output or lock-time.
        """
        b = bytes(self)
        remove_len = self.bitshare_output_length + 4  # 4 is for the lock-time
        return b[:-remove_len]


class CoinbaseTransactionBuilder(object):
    """ See: https://bitcoin.org/en/developer-reference#coinbase
        Builds a coinbase txn:
        Creates a single input with no outpoint. The input script is defined as
        block height, iscript0, enonce1, enonce2, iscript1.

    Args:
        height (int): block height.
        iscript0 (bytes): random bytes provided by the caller.
        iscript1 (bytes): random bytes provided by the caller.
        enonce1_len (int): Length of enonce1 (in bytes). This is usually given
                           by the pool server.
        enonce2_len (int): Length of enonce2 (in bytes). This is usually given
                           by the pool server.
        outputs (list(TransactionOutput)): list of TransactionOutput objects.
        lock_time (int): Time or a block number. Endianness: host
    """

    def __init__(self, height, iscript0, iscript1, enonce1_len, enonce2_len, outputs, lock_time):
        self.height = height
        self.script_prefix = iscript0
        self.script_postfix = iscript1
        self.enonce1_len = enonce1_len
        self.enonce2_len = enonce2_len
        self.outputs = outputs
        self.lock_time = lock_time

        self.bitshare_padding = self.required_padding_for_bitshare()

    def build_placeholder_input(self):
        """ Builds a placeholder input using placeholder enonce1 and enonce2 values.

        Returns:
            cb_inp (CoinbaseInput): the placeholder coinbase input.
        """
        enonce1 = b'\xee' * self.enonce1_len
        enonce2 = b'\xdd' * self.enonce2_len
        return self.build_input(enonce1, enonce2)

    def build_input(self, enonce1, enonce2, padding=None):
        """ Builds a CoinbaseInput, creating the script from the passed-in enonce1 and
            enonce2.
        
        Args:
            enonce1 (bytes): byte stream to place in the coinbase input script. Must be
                             enonce1_len bytes long.
            enonce2 (bytes): byte stream to place in the coinbase input script. Must be
                             enonce2_len bytes long.
            padding (bytes) (Optional): byte stream to pad at the end of the coinbase script. This
                                        is used only for 21 Bitshare devices that require the
                                        Coinbase size without the last output and lock-time to be
                                        a multiple of 512 bits.
         """
        script = self.script_prefix + Script.build_push_str(enonce1 + enonce2) + self.script_postfix
        if padding is not None:
            script += padding
        return CoinbaseInput(self.height, script)

    def required_padding_for_bitshare(self):
        """ Determines the required padding in the input script to make sure
            the length of entire txn *without* the last output & locktime is a
            multiple of 512 bits. This is required to get the coinbase midstate
            to provide to the bitshare hasher.

            For this we assume that the last output is the one added by the
            bitshare hasher and so we ignore that one.

        Returns:
            padding (bytes): The necessary padding for 21 Bitshare devices.
        """
        # build the whole thing including the last output
        placeholder_input = self.build_placeholder_input()
        cb_txn = BitshareCoinbaseTransaction(Transaction.DEFAULT_TRANSACTION_VERSION,
                                             [placeholder_input],
                                             self.outputs,
                                             self.lock_time)

        cb1_len_bits = (len(bytes(cb_txn)) - cb_txn.bitshare_output_length - 4) * 8  # 4 is lock_time length in bytes
        num_bits_padding = (512 - (cb1_len_bits % 512)) % 512
        if num_bits_padding % 8 != 0:
            raise ValueError("Required padding for coinbase input is not a multiple of 8")

        num_bytes_padding = int(num_bits_padding / 8)

        if num_bytes_padding == 0:
            padding = b''
        elif num_bytes_padding == 1:
            padding = b'\x00'
        else:
            padding = bytes([num_bytes_padding - 1]) + bytes(num_bytes_padding - 1)

        return padding

    def build(self, enonce1, enonce2, bitshare=True):
        """ Builds a coinbase txn and returns it. If bitshare == True,
            padding is added to the coinbase input script to align the
            length of the txn without the last output & locktime to a
            512-bit boundary.

        Args:
            enonce1 (bytes): byte stream to place in the coinbase input script. Must be
                             enonce1_len bytes long.
            enonce2 (bytes): byte stream to place in the coinbase input script. Must be
                             enonce2_len bytes long.
            bitshare (bool): True if this will be used for a 21 Bitshare device, False
                             otherwise.
        """

        if len(enonce1) != self.enonce1_len:
            raise ValueError("len(enonce1) does not match enonce1_len")
        if len(enonce2) != self.enonce2_len:
            raise ValueError("len(enonce2) does not match enonce2_len")

        padding = self.bitshare_padding if bitshare else None
        cb_input = self.build_input(enonce1, enonce2, padding)
        tx_type = BitshareCoinbaseTransaction if bitshare else Transaction

        return tx_type(Transaction.DEFAULT_TRANSACTION_VERSION,
                       [cb_input],
                       self.outputs,
                       self.lock_time)
