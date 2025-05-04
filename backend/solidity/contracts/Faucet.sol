// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

error CooldownNotMet();
error InsufficientFaucetBalance();
error OnlyOwner();

contract Faucet {
    address public owner;
    uint256 public maxAmount; // Maximum amount to dispense
    uint256 public cooldownPeriod; // Cooldown period for each address

    mapping(address => uint256) public lastClaimed; // Last claimed timestamp for each address

    event FundsDispensed(address indexed recipient, uint256 amount);
    event MaxAmountUpdated(uint256 newAmount);
    event CooldownUpdated(uint256 newCooldown);
    event Withdraw(address indexed owner, uint256 amount);
    event Received(address indexed from, uint256 amount);

    constructor(uint256 _maxAmount, uint256 _cooldownPeriod) {
        owner = msg.sender;
        maxAmount = _maxAmount;
        cooldownPeriod = _cooldownPeriod;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    function setMaxAmount(uint256 _maxAmount) external onlyOwner {
        maxAmount = _maxAmount;
        emit MaxAmountUpdated(_maxAmount);
    }

    function setCooldownPeriod(uint256 _cooldownPeriod) external onlyOwner {
        cooldownPeriod = _cooldownPeriod;
        emit CooldownUpdated(_cooldownPeriod);
    }

    function dispenseFunds() external {
        if (block.timestamp < lastClaimed[msg.sender] + cooldownPeriod) revert CooldownNotMet();
        if (address(this).balance < maxAmount) revert InsufficientFaucetBalance();

        lastClaimed[msg.sender] = block.timestamp;
        payable(msg.sender).transfer(maxAmount);

        emit FundsDispensed(msg.sender, maxAmount);
    }

    function dispenseTo(address recipient) external onlyOwner {
        if (block.timestamp < lastClaimed[recipient] + cooldownPeriod) revert CooldownNotMet();
        if (address(this).balance < maxAmount) revert InsufficientFaucetBalance();

        lastClaimed[recipient] = block.timestamp;
        payable(recipient).transfer(maxAmount);

        emit FundsDispensed(recipient, maxAmount);
    }

    function withdraw(uint256 amount) external onlyOwner {
        if (address(this).balance < amount) revert InsufficientFaucetBalance();
        payable(owner).transfer(amount);
        emit Withdraw(owner, amount);
    }

    receive() external payable {
        emit Received(msg.sender, msg.value);
    }

    fallback() external payable {
        emit Received(msg.sender, msg.value);
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
