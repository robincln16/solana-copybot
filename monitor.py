import asyncio
import json
import websockets
import httpx
from config import HELIUS_WS_URL, HELIUS_API_KEY, WALLETS_A_COPIER

SOL_MINT = "So11111111111111111111111111111111111111112"

class WalletMonitor:
    def __init__(self, callback_trade):
        self.callback_trade = callback_trade
        self.subscriptions = {}

    async def demarrer(self):
        print(f"[MONITOR] 🔍 Surveillance de {len(WALLETS_A_COPIER)} wallets...")
        while True:
            try:
                ws_url = f"wss://atlas-mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                async with websockets.connect(ws_url) as ws:
                    for wallet in WALLETS_A_COPIER:
                        await self._abonner(ws, wallet)
                        print(f"[MONITOR] ✅ Abonné à {wallet[:8]}...")
                    await self._ecouter(ws)
            except Exception as e:
                print(f"[MONITOR] ⚠️ Déconnexion : {e} — Reconnexion dans 5s...")
                await asyncio.sleep(5)

    async def _abonner(self, ws, wallet_address):
        payload = {
            "jsonrpc": "2.0",
            "id": wallet_address,
            "method": "transactionSubscribe",
            "params": [
                {
                    "accountInclude": [wallet_address],
                    "failed": False
                },
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        }
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
            params = data.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})
            signature = value.get("signature", "")
            transaction = value.get("transaction", {})
            meta = transaction.get("meta", {})

            if not meta or meta.get("err"):
                return

            logs = meta.get("logMessages") or []
            est_swap = any(
                "Program JUP" in log or
                "Program 675kPX" in log or
                "Program 6EF8rr" in log
                for log in logs
            )

            if est_swap:
                print(f"[MONITOR] 🔄 Swap détecté ! {signature[:20]}...")
                trade = self._extraire_swap_direct(meta, signature)
                if trade:
                    print(f"[MONITOR] 💡 Swap : {trade['token_in'][:8]} → {trade['token_out'][:8]}")
                    await self.callback_trade(trade)
                else:
                    print(f"[MONITOR] ⚠️ Pas de swap valide")

        except Exception as e:
            print(f"[MONITOR] ⚠️ Erreur traitement : {e}")

    def _extraire_swap_direct(self, meta, signature):
        try:
            pre_token = meta.get("preTokenBalances") or []
            post_token = meta.get("postTokenBalances") or []
            pre_sol_list = meta.get("preBalances") or []
            post_sol_list = meta.get("postBalances") or []

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
