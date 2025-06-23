#!/usr/bin/env python
"""
Simplified Binance Futures Testnet Trading Bot

Features:
- Place MARKET and LIMIT orders on Binance USDT-M Futures Testnet.
- Supports BUY and SELL sides.
- Command-line interface with argument validation.
- Logs requests, responses, and errors to both console and `bot.log`.

Example usage:
1. Market order:
   python main.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

2. Limit order:
   python main.py --symbol ETHUSDT --side SELL --type LIMIT \
                 --quantity 0.01 --price 2000

API credentials can be supplied via command-line flags or the environment
variables `BINANCE_API_KEY` and `BINANCE_API_SECRET`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional, List

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
LOG_FILE = "bot.log"


def _setup_logger() -> logging.Logger:
    """Configure and return a logger that logs to file and stdout."""
    logger = logging.getLogger("BasicBot")
    logger.setLevel(logging.INFO)

    if logger.handlers:  # Guard against double handlers in REPL tests.
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Stream handler (console)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # Silence overly-verbose loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("binance").setLevel(logging.WARNING)

    return logger


LOGGER = _setup_logger()


class BasicBot:
    """Minimal wrapper around `python-binance` to place Futures orders on testnet."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        # Initialize Client for the USDT-M Futures testnet.
        self.client = Client(api_key, api_secret, base_url=TESTNET_BASE_URL)
        # Explicitly ensure futures endpoints target testnet
        self.client.FUTURES_URL = TESTNET_BASE_URL
        LOGGER.info(
            "Client initialized for Binance Futures testnet @ %s", TESTNET_BASE_URL
        )

    def _log_order(
        self, order_params: Dict[str, Any], response: Dict[str, Any]
    ) -> None:
        LOGGER.info("Order params: %s", json.dumps(order_params))
        LOGGER.info("Order response: %s", json.dumps(response))

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: str = "GTC",
    ) -> Dict[str, Any]:
        """Place an order and return the API response.

        Raises
        ------
        BinanceAPIException | BinanceOrderException
            Upon API errors.
        ValueError
            If parameters are invalid for the selected order type.
        """
        order_params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }

        if order_type.upper() == Client.ORDER_TYPE_LIMIT:
            if price is None:
                raise ValueError("Limit orders require `price`.")
            order_params.update({"price": price, "timeInForce": time_in_force})
        elif order_type.upper() == Client.ORDER_TYPE_MARKET:
            # Market orders need no extra params
            pass
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        LOGGER.info("Placing order: %s", json.dumps(order_params))
        try:
            response = self.client.futures_create_order(**order_params)
            self._log_order(order_params, response)
            return response
        except (BinanceAPIException, BinanceOrderException) as exc:
            LOGGER.error("Binance API error: %s", exc)
            raise


# ---------------------------- CLI helpers --------------------------------- #


def _positive_float(value: str) -> float:
    try:
        f = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if f <= 0:
        raise argparse.ArgumentTypeError("Value must be positive.")
    return f


def parse_cli_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bitestnet",
        description="Binance Futures Testnet Trading Bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # API credentials
    parser.add_argument("--api-key", dest="api_key", help="Binance API key")
    parser.add_argument("--api-secret", dest="api_secret", help="Binance API secret")

    # Order parameters
    parser.add_argument(
        "--symbol", required=True, help="Trading pair symbol, e.g. BTCUSDT"
    )
    parser.add_argument(
        "--side", choices=["BUY", "SELL"], required=True, help="Order side"
    )
    parser.add_argument(
        "--type",
        dest="order_type",
        choices=["MARKET", "LIMIT"],
        required=True,
        help="Order type",
    )
    parser.add_argument(
        "--quantity", type=_positive_float, required=True, help="Order quantity"
    )
    parser.add_argument(
        "--price", type=_positive_float, help="Price (required for LIMIT)"
    )
    parser.add_argument(
        "--tif",
        dest="time_in_force",
        default="GTC",
        choices=["GTC", "IOC", "FOK"],
        help="Time in force (LIMIT orders)",
    )

    return parser.parse_args(argv)


# ------------------------------ Main -------------------------------------- #


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_cli_arguments(argv)

    api_key = args.api_key or os.getenv("BINANCE_API_KEY")
    api_secret = args.api_secret or os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        LOGGER.error(
            "API credentials must be provided via flags or environment variables."
        )
        sys.exit(1)

    bot = BasicBot(api_key, api_secret)

    try:
        response = bot.place_order(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            quantity=args.quantity,
            price=args.price,
            time_in_force=args.time_in_force,
        )
        LOGGER.info("Order successfully executed. ID: %s", response.get("orderId"))
        # Present a concise summary on stdout
        print(json.dumps(response, indent=2))
    except ValueError as exc:
        LOGGER.error("%s", exc)
        sys.exit(2)
    except (BinanceAPIException, BinanceOrderException):
        # Error already logged in BasicBot. Exit with error code.
        sys.exit(3)


if __name__ == "__main__":
    main()
