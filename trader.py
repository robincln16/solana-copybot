import httpx
import base64
import time
from solders.keypair import Keypair
from config import JUPITER_QUOTE_URL, JUPITER_SWAP_URL, HELIUS_RPC_URL, HELIUS_API_KEY, MON_WALLET_PRIVATE_KEY, MONTANT_PAR_TRADE_SOL, SLIPPAGE_BPS, SOL_MINT

class Trader:
    def __init__(self):
        self.keypair = Keypair.from_base58_string(MON_WALLET_PRIVATE_KEY)
        self.wallet_public = str(self.keypair.pubkey())
        self.trades_recents = {}
        self.tokens_achetes = {}  # token_mint -> montant_sol_investi
        print(f"[TRADER] Wallet : {self.wallet_public[:8]}...")

    async def copier_trade(self, trade):
        token_in = trade["token_in"]
        token_out = trade["token_out"]

        # Anti-doublon
        cle = f"{token_in}-{token_out}"
        maintenant = time.time()
        if cle in self.trades_recents:
            if maintenant - self.trades_recents[cle] < 30:
                print(f"[TRADER] ⏭️ Trade doublon ignoré")
                return
        self.trades_recents[cle] = maintenant

        # Détecter si c'est un achat ou une vente
        if token_in == SOL_MINT:
            # ACHAT : SOL → Token
            await self._acheter(token_out)
        elif token_out == SOL_MINT:
            # VENTE : Token → SOL
            await self._vendre(token_in)
        else:
            # Swap token → token, on copie directement
            await self._executer_swap(token_in, token_out, MONTANT_PAR_TRADE_SOL * 1_000_000_000)

    async def _acheter(self, token_mint):
        print(f"[TRADER] 🟢 ACHAT de {token_mint[:8]}...")
        montant = int(MONTANT_PAR_TRADE_SOL * 1_000_000_000)
        signature = await self._executer_swap(SOL_MINT, token_mint, montant)
        if signature:
            self.tokens_achetes[token_mint] = MONTANT_PAR_TRADE_SOL
            print(f"[TRADER] 📝 Token mémorisé : {token_mint[:8]}")

    async def _vendre(self, token_mint):
        if token_mint not in self.tokens_achetes:
            print(f"[TRADER] ⚠️ Token {token_mint[:8]} pas dans notre portefeuille, vente ignorée")
            return

        print(f"[TRADER] 🔴 VENTE de {token_mint[:8]}...")

        # Récupérer le solde réel du token dans notre wallet
        solde = await self._get_token_balance(token_mint)
        if not solde or solde <= 0:
            print(f"[TRADER] ⚠️ Solde nul pour {token_mint[:8]}, vente ignorée")
            del self.tokens_achetes[token_mint]
            return

        signature = await self._executer_swap(token_mint, SOL_MINT, int(solde))
        if signature:
            del self.tokens_achetes[token_mint]
            print(f"[TRADER] 📝 Token vendu et retiré du portefeuille")

    async def _get_token_balance(self, token_mint):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        self.wallet_public,
                        {"mint": token_mint},
                        {"encoding": "jsonParsed"}
                    ]
                }
                reponse = await client.post(url, json=payload)
                data = reponse.json()
                accounts = data.get("result", {}).get("value", [])
                if not accounts:
                    return None
                amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]
                return int(amount)
        except Exception as e:
            print(f"[TRADER] ❌ Erreur récupération solde : {e}")
            return None

    async def _executer_swap(self, token_in, token_out, montant):
        print(f"[TRADER] Copie du trade...")
        try:
            quote = await self._obtenir_quote(token_in, token_out, montant)
            if not quote:
                print("[TRADER] ❌ Pas de quote disponible")
                return None
            if float(quote.get("priceImpactPct", 0)) > 10:
                print("[TRADER] ⚠️ Impact prix trop élevé")
                return None
            transaction = await self._construire_swap(quote)
            if not transaction:
                print("[TRADER] ❌ Impossible de construire le swap")
                return None
            signature = await self._envoyer_transaction(transaction)
            if signature:
                print(f"[TRADER] ✅ Trade exécuté !")
                print(f"[TRADER] 🔗 https://solscan.io/tx/{signature}")
            return signature
        except Exception as e:
            print(f"[TRADER] Erreur : {e}")
            return None

    async def _obtenir_quote(self, token_in, token_out, montant):
        try:
            params = {
                "inputMint": token_in,
                "outputMint": token_out,
                "amount": montant,
                "slippageBps": SLIPPAGE_BPS
            }
            async with httpx.AsyncClient(timeout=30) as client:
                reponse = await client.get(JUPITER_QUOTE_URL, params=params)
                print(f"[TRADER] 📡 Quote status : {reponse.status_code}")
                data = reponse.json()
                if "error" in data:
                    print(f"[TRADER] ⚠️ Erreur quote : {data['error']}")
                    return None
                return data
        except Exception as e:
            print(f"[TRADER] ❌ Erreur quote : {e}")
            return None

    async def _construire_swap(self, quote):
        try:
            payload = {
                "quoteResponse": quote,
                "userPublicKey": self.wallet_public,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": 5000
            }
            async with httpx.AsyncClient(timeout=30) as client:
                reponse = await client.post(JUPITER_SWAP_URL, json=payload)
                print(f"[TRADER] 📡 Swap status : {reponse.status_code}")
                data = reponse.json()
                if "swapTransaction" not in data:
                    print(f"[TRADER] ⚠️ Pas de swapTransaction : {data}")
                    return None
                return data["swapTransaction"]
        except Exception as e:
            print(f"[TRADER] ❌ Erreur swap : {e}")
            return None

    async def _envoyer_transaction(self, swap_b64):
        try:
            from solders.transaction import VersionedTransaction
            tx_bytes = base64.b64decode(swap_b64)
            tx = VersionedTransaction.from_bytes(tx_bytes)
            tx_signe = VersionedTransaction(tx.message, [self.keypair])
            tx_encode = base64.b64encode(bytes(tx_signe)).decode()
            async with httpx.AsyncClient(timeout=30) as client:
                url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                reponse = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [tx_encode, {"encoding": "base64", "skipPreflight": True}]
                    }
                )
                data = reponse.json()
                print(f"[TRADER] 📡 Send status : {reponse.status_code}")
                if "result" in data:
                    return data["result"]
                print(f"[TRADER] ⚠️ Erreur envoi : {data}")
                return None
        except Exception as e:
            print(f"[TRADER] ❌ Erreur envoi : {e}")
            return None

    async def fermer(self):
        pass
