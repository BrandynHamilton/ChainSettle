// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract ValidatorRegistry {
    mapping(address => bool) public isValidator;
    address[] public validatorList;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can modify validators");
        _;
    }

    function registerValidator(address validator) external onlyOwner {
        require(!isValidator[validator], "Already registered");
        isValidator[validator] = true;
        validatorList.push(validator);
    }

    function unregisterValidator(address validator) external onlyOwner {
        require(isValidator[validator], "Not registered");
        isValidator[validator] = false;
    }

    function checkValidator(address validator) external view returns (bool) {
        return isValidator[validator];
    }

    function getValidatorCount() external view returns (uint256 count) {
        for (uint256 i = 0; i < validatorList.length; i++) {
            if (isValidator[validatorList[i]]) {
                count++;
            }
        }
    }

    function getValidators() external view returns (address[] memory) {
        return validatorList;
    }
}
