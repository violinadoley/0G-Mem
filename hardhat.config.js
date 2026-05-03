require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    // 0G Galileo Testnet (v3, Chain ID 16601)
    "0g-testnet": {
      url: "https://evmrpc-testnet.0g.ai",
      chainId: 16602,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
    },
    // 0G Newton Testnet (v2, Chain ID 16600) — kept for reference
    "0g-newton": {
      url: "https://evmrpc-testnet.0g.ai",
      chainId: 16600,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
    },
    // Local hardhat for testing
    hardhat: {
      chainId: 31337,
    },
  },
  etherscan: {
    apiKey: {
      "0g-testnet": "no-api-key-needed",
    },
    customChains: [
      {
        network: "0g-testnet",
        chainId: 16601,
        urls: {
          apiURL: "https://chainscan-galileo.0g.ai/api",
          browserURL: "https://chainscan-galileo.0g.ai",
        },
      },
      {
        network: "0g-newton",
        chainId: 16600,
        urls: {
          apiURL: "https://chainscan-newton.0g.ai/api",
          browserURL: "https://chainscan-newton.0g.ai",
        },
      },
    ],
  },
  paths: {
    sources: "./contracts",
    tests: "./contracts/test",
    artifacts: "./contracts/artifacts",
  },
};
