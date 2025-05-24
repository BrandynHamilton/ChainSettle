// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

import "./SettlementRegistry.sol";

contract SettlementConsumer {
    SettlementRegistry public immutable registry;

    event ConsumerAlert(bytes32 indexed idHash, address indexed counterparty, string sType, string settlementId, uint256 , string metadata);

    constructor(address _registry) {
        registry = SettlementRegistry(_registry);
    }

    // Called by an external actor (or Automation) to pull and forward a settlement
    function pullSettlement(string calldata settlementId) external {
        bytes32 idHash = keccak256(abi.encodePacked(settlementId));
        // Read the on-chain struct
        (
            , 
            string memory sType,
            SettlementRegistry.Status status,
            string memory metadata,
            uint256 amount, 
            address payer
        ) = registry.getSettlementById(settlementId);

        require(status == SettlementRegistry.Status.Confirmed, "Not confirmed");
        // Emit a higher-level consumer event
        emit ConsumerAlert(idHash, payer, sType, settlementId, amount, metadata);
    }
}
