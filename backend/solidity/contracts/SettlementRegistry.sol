// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

interface IValidatorRegistry {
    function isValidator(address validator) external view returns (bool);
    function getValidatorCount() external view returns (uint256 count);
}

contract SettlementRegistry {
    enum Status { Unverified, Confirmed, Failed }

    struct Settlement {
        string settlementId;
        string settlementType;
        Status status;     // last owner proposal
        string metadata;
        uint256 amount;
    }

    IValidatorRegistry public validatorRegistry;
    address public owner;

    // Owner proposals
    mapping(string => Settlement) public settlements;
    string[] public settlementIds;

    // Voting state
    mapping(string => mapping(address => bool))  public hasVoted;
    mapping(string => uint256)                   public agreeVotes;
    mapping(string => uint256)                   public disagreeVotes;
    mapping(string => bool)                      public finalized;
    mapping(string => bool)                      public confirmedLock;  // lock only on true Confirmed

    // Proposal / vote nonces, to allow re-voting on new proposals
    mapping(string => uint256)                   public proposalNonce;
    mapping(string => mapping(address => uint256)) public lastVotedNonce;

    event SettlementInitialized(string indexed settlementId, string settlementType, string metadata, uint256 amount);
    event Attested(            string indexed settlementId, string settlementType, Status status,   string metadata, uint256 amount);
    event SettlementValidated( string indexed settlementId, Status finalStatus);

    modifier onlyOwner() {
        require(msg.sender == owner, "Unauthorized");
        _;
    }

    constructor(address _validatorRegistry) {
        owner = msg.sender;
        validatorRegistry = IValidatorRegistry(_validatorRegistry);
    }

    function initAttest(
        string calldata settlementId,
        string calldata settlementType,
        string calldata metadata,
        uint256      amount
    ) external onlyOwner {
        require(bytes(settlements[settlementId].settlementId).length == 0, "Already initialized");
        settlements[settlementId] = Settlement(settlementId, settlementType, Status.Unverified, metadata, amount);
        settlementIds.push(settlementId);
        emit SettlementInitialized(settlementId, settlementType, metadata, amount);
    }

    function attest(
        string calldata settlementId,
        string calldata settlementType,
        Status        statusProposal,
        string calldata metadata,
        uint256       amount
    ) external onlyOwner {
        require(bytes(settlements[settlementId].settlementId).length != 0,     "Not initialized");
        require(!confirmedLock[settlementId],                                  "Already confirmed");

        // Update owner’s proposal
        settlements[settlementId] = Settlement(settlementId, settlementType, statusProposal, metadata, amount);

        // Reset voting state for this new proposal
        proposalNonce[settlementId] += 1;
        agreeVotes[settlementId]    = 0;
        disagreeVotes[settlementId] = 0;
        finalized[settlementId]     = false;

        emit Attested(settlementId, settlementType, statusProposal, metadata, amount);
    }

    function voteOnSettlement(string calldata settlementId, bool agree) external {
        require(validatorRegistry.isValidator(msg.sender), "Not a validator");
        require(lastVotedNonce[settlementId][msg.sender] < proposalNonce[settlementId],
                "Already voted this round");
        require(!finalized[settlementId], "Already finalized");

        // record vote
        lastVotedNonce[settlementId][msg.sender] = proposalNonce[settlementId];
        if (agree) {
            agreeVotes[settlementId] += 1;
        } else {
            disagreeVotes[settlementId] += 1;
        }

        uint256 totalValidators = validatorRegistry.getValidatorCount();
        // ceil(2/3 * totalValidators) = (2*TV + 2)/3
        uint256 threshold = (2 * totalValidators + 2) / 3;

        // finalize as soon as one side hits threshold
        if (agreeVotes[settlementId] >= threshold) {
            _finalize(settlementId, true);
        } else if (disagreeVotes[settlementId] >= threshold) {
            _finalize(settlementId, false);
        }
    }

    function _finalize(string calldata settlementId, bool didAgree) private {
        finalized[settlementId] = true;

        // Only lock further attest() calls when the owner truly proposed Confirmed
        if (didAgree && settlements[settlementId].status == Status.Confirmed) {
            confirmedLock[settlementId] = true;
        }

        // Always maintain the owner's proposal (Confirmed or Failed)
        Status finalStatus = settlements[settlementId].status;

        settlements[settlementId].status = finalStatus;
        emit SettlementValidated(settlementId, finalStatus);
    }

    function getSettlement(string calldata settlementId) external view returns (Settlement memory) {
        return settlements[settlementId];
    }
    
    /// @notice Return all initialized settlement IDs
    function getSettlementIds() external view returns (string[] memory) {
        return settlementIds;
    }

    function isValidator(address _addr) public view returns (bool) {
        return validatorRegistry.isValidator(_addr);
    }

    function getValidatorCount() public view returns (uint256) {
        return validatorRegistry.getValidatorCount();
    }
}
