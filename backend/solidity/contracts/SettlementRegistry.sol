// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

interface IValidatorRegistry {
    function isValidator(address validator) external view returns (bool);
    function getValidatorCount() external view returns (uint256 count);
}

contract SettlementRegistry {
    address public owner;

    enum Status { Unverified, Confirmed, Failed }

    struct Settlement {
        string settlementId;
        string settlementType;
        Status status;
        string metadata; // could store tag, docURI, etc.
        uint256 amount; // optional; use 0 if not needed
    }

    mapping(string => Settlement) public settlements;
    mapping(string => mapping(address => bool)) public hasVoted;  // settlementId => voter => hasVoted
    mapping(string => uint256) public confirmVotes;  // settlementId => number of confirms
    mapping(string => uint256) public rejectVotes;   // settlementId => number of rejects
    mapping(string => bool) public finalized;        // settlementId => finalized?

    event SettlementInitialized(string settlementId, string settlementType, string metadata, uint256 amount);
    event Attested(string settlementId, string settlementType, Status status, string metadata, uint256 amount);
    event SettlementFinalized(string settlementId, Status finalStatus);

    IValidatorRegistry public validatorRegistry;

    constructor(address _validatorRegistry) {
        owner = msg.sender;
        validatorRegistry = IValidatorRegistry(_validatorRegistry);
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Unauthorized");
        _;
    }

    function initAttest(
        string calldata settlementId,
        string calldata settlementType,
        string calldata metadata,
        uint256 amount
    ) external onlyOwner {
        require(bytes(settlements[settlementId].settlementId).length == 0, "Already initialized");

        settlements[settlementId] = Settlement({
            settlementId: settlementId,
            settlementType: settlementType,
            status: Status.Unverified,
            metadata: metadata,
            amount: amount
        });

        emit SettlementInitialized(settlementId, settlementType, metadata, amount);
    }

    function attest(
        string calldata settlementId,
        string calldata settlementType,
        Status status,
        string calldata metadata,
        uint256 amount
    ) external onlyOwner {
        require(bytes(settlements[settlementId].settlementId).length != 0, "Not initialized");
        require(settlements[settlementId].status != Status.Confirmed, "Already confirmed");

        settlements[settlementId] = Settlement({
            settlementId: settlementId,
            settlementType: settlementType,
            status: status,
            metadata: metadata,
            amount: amount
        });

        emit Attested(settlementId, settlementType, status, metadata, amount);
    }

    function voteOnSettlement(string calldata settlementId, bool confirm) external {
        require(isValidator(msg.sender), "Not a validator");
        require(!hasVoted[settlementId][msg.sender], "Already voted");
        require(!finalized[settlementId], "Already finalized");

        hasVoted[settlementId][msg.sender] = true;

        if (confirm) {
            confirmVotes[settlementId] += 1;
        } else {
            rejectVotes[settlementId] += 1;
        }

        uint256 totalValidators = getValidatorCount();
        uint256 totalVotes = confirmVotes[settlementId] + rejectVotes[settlementId];
        uint256 minVotes = totalValidators < 3 ? totalValidators : 3;
        uint256 threshold = (2 * totalValidators) / 3 + 1;

        if (totalVotes >= minVotes) {
            finalized[settlementId] = true;
            if (confirmVotes[settlementId] >= threshold) {
                settlements[settlementId].status = Status.Confirmed;
            } else {
                settlements[settlementId].status = Status.Failed;
            }
            emit SettlementFinalized(settlementId, settlements[settlementId].status);
        }
    }

    function isValidator(address _addr) public view returns (bool) {
        return validatorRegistry.isValidator(_addr);
    }

    function getValidatorCount() public view returns (uint256) {
        return validatorRegistry.getValidatorCount();
    }

}
