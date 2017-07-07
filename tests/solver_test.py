import hashlib
import unittest

from pycoin.coins.bitcoin.ScriptTools import BitcoinScriptTools
from pycoin.coins.bitcoin.Solver import Solver
from pycoin.coins.bitcoin.SolutionChecker import check_solution

from pycoin.key import Key
from pycoin.serialize import b2h
from pycoin.tx.Tx import Tx, TxIn, TxOut

from pycoin.tx.pay_to import (
    ScriptMultisig, ScriptPayToPublicKey, build_hash160_lookup, build_p2sh_lookup
)
from pycoin.tx.script import ScriptError

from pycoin.ui import address_for_pay_to_script, standard_tx_out_script


class SolverTest(unittest.TestCase):

    def do_test_solve(self, tx, tx_in_idx, **kwargs):
        solver = Solver(tx)
        constraints = solver.determine_constraints(tx_in_idx, p2sh_lookup=kwargs.get("p2sh_lookup"))
        solution_list, witness_list = solver.solve_for_constraints(constraints, **kwargs)
        solution_script = BitcoinScriptTools.compile_push_data_list(solution_list)
        tx.txs_in[tx_in_idx].script = solution_script
        tx.txs_in[tx_in_idx].witness = witness_list
        if not kwargs.get("nocheck"):
            check_solution(tx, tx_in_idx)
        return solution_script, witness_list

    def make_test_tx(self, input_script):
        previous_hash = b'\1' * 32
        txs_in = [TxIn(previous_hash, 0)]
        txs_out = [TxOut(1000, standard_tx_out_script(Key(1).address()))]
        version, lock_time = 1, 0
        tx = Tx(version, txs_in, txs_out, lock_time)
        unspents = [TxOut(1000, input_script)]
        tx.set_unspents(unspents)
        return tx

    def do_test_tx(self, incoming_script, **kwargs):
        keys = [Key(i) for i in range(1, 20)]
        tx = self.make_test_tx(incoming_script)
        tx_in_idx = 0
        kwargs["hash160_lookup"] = build_hash160_lookup(k.secret_exponent() for k in keys)
        self.do_test_solve(tx, tx_in_idx, **kwargs)

    def test_p2pkh(self):
        key = Key(1)
        self.do_test_tx(standard_tx_out_script(key.address()))

    def test_p2pk(self):
        key = Key(1)
        self.do_test_tx(ScriptPayToPublicKey.from_key(key).script())

    def test_nonstandard_p2pkh(self):
        key = Key(1)
        self.do_test_tx(BitcoinScriptTools.compile("OP_SWAP") + standard_tx_out_script(key.address()))

    def test_p2multisig(self):
        keys = [Key(i) for i in (1, 2, 3)]
        secs = [k.sec() for k in keys]
        self.do_test_tx(ScriptMultisig(2, secs).script())

    def test_p2sh(self):
        keys = [Key(i) for i in (1, 2, 3)]
        secs = [k.sec() for k in keys]
        underlying_script = ScriptMultisig(1, secs).script()
        script = standard_tx_out_script(address_for_pay_to_script(underlying_script))
        self.do_test_tx(script, p2sh_lookup=build_p2sh_lookup([underlying_script]))

        underlying_script = BitcoinScriptTools.compile("OP_SWAP") + standard_tx_out_script(keys[0].address())
        script = standard_tx_out_script(address_for_pay_to_script(underlying_script))
        self.do_test_tx(script, p2sh_lookup=build_p2sh_lookup([underlying_script]))

        underlying_script = ScriptPayToPublicKey.from_key(keys[2]).script()
        script = standard_tx_out_script(address_for_pay_to_script(underlying_script))
        self.do_test_tx(script, p2sh_lookup=build_p2sh_lookup([underlying_script]))

    def test_p2pkh_wit(self):
        key = Key(1)
        script = BitcoinScriptTools.compile("OP_0 [%s]" % b2h(key.hash160()))
        self.do_test_tx(script)

    def test_p2sh_wit(self):
        keys = [Key(i) for i in (1, 2, 3)]
        secs = [k.sec() for k in keys]
        underlying_script = ScriptMultisig(2, secs).script()
        script = BitcoinScriptTools.compile("OP_0 [%s]" % b2h(hashlib.sha256(underlying_script).digest()))
        self.do_test_tx(script, p2sh_lookup=build_p2sh_lookup([underlying_script]))

    def test_p2multisig_wit(self):
        keys = [Key(i) for i in (1, 2, 3)]
        secs = [k.sec() for k in keys]
        underlying_script = ScriptMultisig(2, secs).script()
        p2sh_script = BitcoinScriptTools.compile("OP_0 [%s]" % b2h(hashlib.sha256(underlying_script).digest()))
        script = standard_tx_out_script(address_for_pay_to_script(p2sh_script))
        self.do_test_tx(script, p2sh_lookup=build_p2sh_lookup([underlying_script, p2sh_script]))

    def test_if(self):
        script = BitcoinScriptTools.compile("IF 1 ELSE 0 ENDIF")
        # self.do_test_tx(script)

    def test_p2multisig_incremental(self):
        keys = [Key(i) for i in (1, 2, 3)]
        secs = [k.sec() for k in keys]
        tx = self.make_test_tx(ScriptMultisig(3, secs).script())
        tx_in_idx = 0
        for k in keys:
            try:
                check_solution(tx, tx_in_idx)
                assert 0
            except ScriptError:
                pass
            kwargs = {"hash160_lookup": build_hash160_lookup([k.secret_exponent()])}
            kwargs["existing_script"] = [
                data for opcode, data, pc, new_pc in BitcoinScriptTools.get_opcodes(
                    tx.txs_in[tx_in_idx].script) if data is not None]
            kwargs["nocheck"] = True
            solution_list, witness_list = self.do_test_solve(tx, tx_in_idx, **kwargs)
        check_solution(tx, tx_in_idx)


if __name__ == "__main__":
    unittest.main()
