import asyncio
import json
import websockets
import httpx
from datetime import datetime
from config import HELIUS_WS_URL, HELIUS_RPC_URL, HELIUS_API_KEY, WALLETS_A_COPIER, DELAI_MAX_COPIE_SEC

SOL_MINT = "So11111111111111111111111111111111111111112"

class WalletMonitor:
    def __init__(self, callback_trade):
        self.callback_trade = callback_trade
        self.subscriptions = {}

    async def demarrer(self):
        print(f"[MONITOR] 🔍 Surveillance de {len(WALLETS_A_COPIER)} wallets...")
        while True:
            try:
                async with websockets.connect(HELIUS_WS_URL) as ws:
                    for wallet in WALLETS_A_COPIER:
                        await self._abonner(ws, wallet)
                        print(f"[MONITOR] ✅ Abonné à {wallet[:8]}...")
                    await self._ecouter(ws)
            except Exception as e:
                print(f"[MONITOR] ⚠️ Déconnexion : {e} — Reconnexion dans 5s...")
                await asyncio.sleep(5)

    async def _abonner(self, ws, wallet_address):
        payload = {"jsonrpc": "2.0", "id": wallet_address, "method": "logsSubscribe", "params": [{"mentions": [wallet_address]}, {"commitment": "confirmed"}]}
        await ws.send(json.dumps(payload))
        reponse = json.loads(await ws.recv())
        if "result" in reponse:
            self.subscriptions[wallet_address] = reponse["result"]

    async def _ecouter(self, ws):
        print("[MONITOR] 👂 En attente de transactions...")
        async for message in ws:
            try:
                data = json.loads(message)
                await self._traiter_message(data)
            except Exception as e:
                print(f"[MONITOR] ⚠️ Erreur écoute : {e}")

    async def _traiter_message(self, data):
        if "result" in data:
            return
        try:
            logs = data["params"]["result"]["value"]["logs"]
            signature = data["params"]["result"]["value"]["signature"]
            est_swap = any(
                "Program JUP" in log or
                "Program 675kPX" in log or
                "Program 6EF8rr" in log
                for log in logs
            )
            if est_swap:
                print(f"[MONITOR] 🔄 Swap détecté ! {signature[:20]}...")
                asyncio.create_task(self._analyser_transaction(signature))
        except (KeyError, TypeError):
            pass

    async def _analyser_transaction(self, signature):
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                }
                for tentative in range(5):
                    await asyncio.sleep(3)
                    print(f"[MONITOR] 🔍 Tentative {tentative+1} pour {signature[:20]}...")
                    reponse = await client.post(url, json=payload, timeout=15)
                    data = reponse.json()
                    tx = data.get("result")
                    if tx:
                        print(f"[MONITOR] 📋 Transaction trouvée à la tentative {tentative+1} !")
                        trade = self._extraire_swap(tx, signature)
                        if trade:
                            print(f"[MONITOR] 💡 Swap : {trade['token_in'][:8]} → {trade['token_out'][:8]}")
                            await self.callback_trade(trade)
                        else:
                            print(f"[MONITOR] ⚠️ Pas de swap valide")
                        return
                    print(f"[MONITOR] ⏳ Pas encore disponible, on réessaie...")
                print(f"[MONITOR] ❌ Transaction introuvable après 5 tentatives")
        except Exception as e:
            print(f"[MONITOR] ❌ Erreur analyse : {e}")

    def _extraire_swap(self, tx, signature):
        try:
            meta = tx["meta"]
            pre_token = meta.get("preTokenBalances") or []
            post_token = meta.get("postTokenBalances") or []
            pre_sol_list = meta.get("preBalances") or []
            post_sol_list = meta.get("postBalances") or []

            # Token balances
            pre = {}
            for b in pre_token:
                mint = b.get("mint")
                amount = b.get("uiTokenAmount", {}).get("uiAmount")
                if mint and amount is not None:
                    pre[mint] = float(amount)

            post = {}
            for b in post_token:
                mint = b.get("mint")
                amount = b.get("uiTokenAmount", {}).get("uiAmount")
                if mint and amount is not None:
                    post[mint] = float(amount)

            # Trouver le plus grand changement SOL dans toutes les balances
            max_sol_diff = 0
            for i in range(min(len(pre_sol_list), len(post_sol_list))):
                diff = (post_sol_list[i] - pre_sol_list[i]) / 1e9
                if abs(diff) > abs(max_sol_diff):
                    max_sol_diff = diff

            token_in = None
            token_out = None
            montant_in = 0
            montant_out = 0

            tous_mints = set(pre.keys()) | set(post.keys())
            for mint in tous_mints:
                avant = pre.get(mint, 0) or 0
                apres = post.get(mint, 0) or 0
                diff = apres - avant
                if diff < -0.000001:
                    token_in = mint
                    montant_in = abs(diff)
                elif diff > 0.000001:
                    token_out = mint
                    montant_out = diff

            # Compléter avec SOL si nécessaire
            if token_in and not token_out:
                token_out = SOL_MINT
                montant_out = abs(max_sol_diff)

            if token_out and not token_in:
                token_in = SOL_MINT
                montant_in = abs(max_sol_diff)

            if not token_in and not token_out:
                if max_sol_diff < -0.001:
                    token_in = SOL_MINT
                    montant_in = abs(max_sol_diff)
                elif max_sol_diff > 0.001:
                    token_out = SOL_MINT
                    montant_out = max_sol_diff

            print(f"[MONITOR] 🔎 token_in={token_in} token_out={token_out} sol_diff={max_sol_diff:.4f}")

            if token_in and token_out and token_in != token_out:
                return {
                    "signature": signature,
                    "token_in": token_in,
                    "token_out": token_out,
                    "montant_in": montant_in,
                    "montant_out": montant_out,
                }
            return None

        except Exception as e:
            print(f"[MONITOR] ⚠️ Erreur extraction : {e}")
            return None
