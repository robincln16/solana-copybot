import asyncio
import json
import websockets
import httpx
from datetime import datetime
from config import HELIUS_WS_URL, HELIUS_RPC_URL, HELIUS_API_KEY, WALLETS_A_COPIER, DELAI_MAX_COPIE_SEC

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
            await asyncio.sleep(3)
            print(f"[MONITOR] 🔍 Analyse de {signature[:20]}...")
            async with httpx.AsyncClient() as client:
                url = f"https://api.helius.xyz/v0/transactions?api-key={HELIUS_API_KEY}"
                payload = {"transactions": [signature]}
                reponse = await client.post(url, json=payload, timeout=15)
                print(f"[MONITOR] 📡 Status Helius : {reponse.status_code}")
                data = reponse.json()
                print(f"[MONITOR] 📦 Réponse : {str(data)[:100]}")
                if not data or len(data) == 0:
                    print(f"[MONITOR] ❌ Transaction introuvable")
                    return
                tx = data[0]
                transfers = tx.get("tokenTransfers", [])
                print(f"[MONITOR] 🔁 Transfers trouvés : {len(transfers)}")
                if len(transfers) < 2:
                    print(f"[MONITOR] ⚠️ Pas assez de transfers")
                    return
                token_in = transfers[0].get("mint", "")
                token_out = transfers[-1].get("mint", "")
                montant_in = transfers[0].get("tokenAmount", 0)
                montant_out = transfers[-1].get("tokenAmount", 0)
                if not token_in or not token_out:
                    print(f"[MONITOR] ⚠️ Tokens manquants")
                    return
                print(f"[MONITOR] 💡 Swap : {token_in[:8]} → {token_out[:8]}")
                await self.callback_trade({
                    "signature": signature,
                    "token_in": token_in,
                    "token_out": token_out,
                    "montant_in": montant_in,
                    "montant_out": montant_out,
                })
        except Exception as e:
            print(f"[MONITOR] ❌ Erreur analyse : {e}")

    def _extraire_swap(self, tx, signature):
        try:
            meta = tx["meta"]
            pre = {b["mint"]: b["uiTokenAmount"]["uiAmount"] for b in (meta.get("preTokenBalances") or []) if b.get("uiTokenAmount", {}).get("uiAmount") is not None}
            post = {b["mint"]: b["uiTokenAmount"]["uiAmount"] for b in (meta.get("postTokenBalances") or []) if b.get("uiTokenAmount", {}).get("uiAmount") is not None}
            token_in = token_out = None
            montant_in = montant_out = 0
            for mint in set(pre.keys()) | set(post.keys()):
                diff = (post.get(mint, 0) or 0) - (pre.get(mint, 0) or 0)
                if diff < -0.001:
                    token_in, montant_in = mint, abs(diff)
                elif diff > 0.001:
                    token_out, montant_out = mint, diff
            if token_in and token_out:
                return {"signature": signature, "token_in": token_in, "token_out": token_out, "montant_in": montant_in, "montant_out": montant_out}
            return None
        except Exception as e:
            print(f"[MONITOR] ⚠️ Erreur extraction : {e}")
            return None
