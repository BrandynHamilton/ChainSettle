// SPDX-License-Identifier: MIT

pragma solidity ^0.8.20;

contract SettlementRegistry{

    address public owner;

    struct Settlement {

        string escrowId;

        uint256 amount;

    }

    mapping(string => Settlement) public settlements;

    event ActionAttested(string escrowId, uint256 amount);

    constructor(
         
    ){
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    function attest(string calldata escrowId, uint256 amount) external onlyOwner {

        settlements[escrowId] = Settlement (escrowId ,amount );
        emit ActionAttested(escrowId, amount);
    }
}