import httpx
import base64
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from config import JUPITER_QUOTE_URL, JUPITER_SWAP_URL, HELIUS_RPC_URL, MON_WALLET_PRIVATE_KEY, MONTANT_PAR_TRADE_SOL, SLIPPAGE_BPS

class Trader:
    def __init__(self):
        self.keypair = Keypair.from_base58_string(MON_WALLET_PRIVATE_KEY)
        self.wallet_public = str(self.keypair.pubkey())
        self.client = AsyncClient(HELIUS_RPC_URL)
        print(f"[TRADER] Wallet : {self.wallet_public[:8]}...")

    async def copier_trade(self, trade):
        print(f"[TRADER] Copie du trade...")
        try:
            quote = await self._obtenir_quote(trade["token_in"], trade["token_out"])
            if not quote:
                return
            if float(quote.get("priceImpactPct", 0)) > 5:
                print("[TRADER] Impact prix trop eleve")
                return
            transaction = await self._construire_swap(quote)
            if not transaction:
                return
            signature = await self._envoyer_transaction(transaction)
            if signature:
                print(f"[TRADER] Trade execute ! https://solscan.io/tx/{signature}")
        except Exception as e:
            print(f"[TRADER] Erreur : {e}")

    async def _obtenir_quote(self, token_in, token_out):
        montant = int(MONTANT_PAR_TRADE_SOL * 1_000_000_000)
        params = {"inputMint": token_in, "outputMint": token_out, "amount": montant, "slippageBps": SLIPPAGE_BPS}
        async with httpx.AsyncClient() as client:
            reponse = await client.get(JUPITER_QUOTE_URL, params=params, timeout=10)
            data = reponse.json()
            if "error" in data:
                return None
            return data

    async def _construire_swap(self, quote):
        payload = {"quoteResponse": quote, "userPublicKey": self.wallet_public, "wrapAndUnwrapSol": True, "dynamicComputeUnitLimit": True, "prioritizationFeeLamports": 1000}
        async with httpx.AsyncClient() as client:
            reponse = await client.post(JUPITER_SWAP_URL, json=payload, timeout=15)
            data = reponse.json()
            if "swapTransaction" not in data:
                return None
            return data["swapTransaction"]

    async def _envoyer_transaction(self, swap_b64):
        from solders.transaction import VersionedTransaction
        tx_bytes = base64.b64decode(swap_b64)
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx_signe = VersionedTransaction(tx.message, [self.keypair])
        resultat = await self.client.send_raw_transaction(bytes(tx_signe))
        return str(resultat.value)

    async def fermer(self):
        await self.client.close()
