/**
 * Deploy MemoryRegistry + MemoryNFT to 0G Chain.
 *
 * Usage:
 *   npx hardhat run contracts/scripts/deploy.js --network 0g-testnet
 *
 * After deploying, update ogmem/config.py with both contract addresses.
 */

const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts...");
  console.log("Deployer:", deployer.address);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance:", hre.ethers.formatEther(balance), "A0GI");

  if (balance === 0n) {
    console.error("\n❌ Deployer has no balance.");
    console.error("Get testnet tokens at: https://faucet.0g.ai");
    process.exit(1);
  }

  // Deploy MemoryRegistry (verifiable audit trail)
  const MemoryRegistry = await hre.ethers.getContractFactory("MemoryRegistry");
  const registry = await MemoryRegistry.deploy();
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();
  console.log("\n✅ MemoryRegistry deployed to:", registryAddress);

  // Deploy MemoryNFT (ERC-7857 ownership + shard access control)
  const MemoryNFT = await hre.ethers.getContractFactory("MemoryNFT");
  const nft = await MemoryNFT.deploy();
  await nft.waitForDeployment();
  const nftAddress = await nft.getAddress();
  console.log("✅ MemoryNFT deployed to:      ", nftAddress);

  console.log("\n   Network: 0G Galileo Testnet (Chain ID 16601)");
  console.log("   Explorer (Registry):", `https://chainscan-galileo.0g.ai/address/${registryAddress}`);
  console.log("   Explorer (NFT):     ", `https://chainscan-galileo.0g.ai/address/${nftAddress}`);

  console.log("\nNext step — add to VerifiableMemory constructor:");
  console.log(`   registry_contract_address="${registryAddress}"`);
  console.log(`   nft_contract_address="${nftAddress}"`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
