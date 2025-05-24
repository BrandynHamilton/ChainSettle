// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

interface IValidatorRegistry {
    function isValidator(address validator) external view returns (bool);
    function getValidatorCount() external view returns (uint256 count);
}

contract SettlementRegistry {
    enum Status { Unverified, Confirmed, Failed }

    struct Settlement {
        string settlementId;    // full text
        string settlementType;
        Status status;          // last owner proposal
        string metadata;
        uint256 amount;
        address payer; // optional
    }

    IValidatorRegistry public immutable validatorRegistry;
    address public immutable owner;

    // key the mapping by the hash of settlementId
    mapping(bytes32 => Settlement)           public settlements;
    bytes32[]                                public settlementIdHashes;
    string[]                                 public settlementIds;

    // voting / re-proposal state (unchanged)
    mapping(bytes32 => mapping(address => bool))  public hasVoted;
    mapping(bytes32 => uint256)                   public agreeVotes;
    mapping(bytes32 => uint256)                   public disagreeVotes;
    mapping(bytes32 => bool)                      public finalized;
    mapping(bytes32 => bool)                      public confirmedLock;
    mapping(bytes32 => uint256)                   public proposalNonce;
    mapping(bytes32 => mapping(address => uint256)) public lastVotedNonce;

    mapping(address => bytes32[]) private _settlementsByPayer;

    // now index only the fixed-size hash
    event SettlementInitialized(
      bytes32 indexed idHash,
      address  indexed payer,
      string   settlementId,
      string   settlementType,
      string   metadata,
      uint256  amount
    );
    event Attested(
      bytes32 indexed idHash,
      address  indexed payer,
      string   settlementId,
      string   settlementType,
      Status   statusProposal,
      string   metadata,
      uint256  amount
      
    );
    event SettlementValidated(
      bytes32 indexed idHash,
      string   settlementId,
      Status   finalStatus
    );

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
        uint256      amount,
        address       payer
    ) external onlyOwner {
        bytes32 idHash = keccak256(abi.encodePacked(settlementId));
        require(bytes(settlements[idHash].settlementId).length == 0, "Already initialized");

        settlements[idHash] = Settlement(settlementId, settlementType, Status.Unverified, metadata, amount, payer);
        settlementIdHashes.push(idHash);
        settlementIds.push(settlementId);

        _settlementsByPayer[payer].push(idHash);

        emit SettlementInitialized(idHash, payer, settlementId, settlementType, metadata, amount);
    }

    function attest(
        string calldata settlementId,
        Status        statusProposal,
        string calldata metadata,
        uint256       amount
    ) external onlyOwner {
        bytes32 idHash = keccak256(abi.encodePacked(settlementId));
        require(bytes(settlements[idHash].settlementId).length != 0, "Not initialized");
        require(!confirmedLock[idHash], "Already confirmed");

        address payer = settlements[idHash].payer; // We need to keep the payer from the original initAttest
        string memory settlementType = settlements[idHash].settlementType; // We need to keep the settlementType from the original initAttest


        // overwrite the owner proposal
        settlements[idHash] = Settlement(settlementId, settlementType, statusProposal, metadata, amount, payer);

        // reset for a fresh voting round
        proposalNonce[idHash]   += 1;
        agreeVotes[idHash]       = 0;
        disagreeVotes[idHash]    = 0;
        finalized[idHash]        = false;

        emit Attested(idHash, payer, settlementId, settlementType, statusProposal, metadata, amount);
    }

    function voteOnSettlement(string calldata settlementId, bool agree) external {
        bytes32 idHash = keccak256(abi.encodePacked(settlementId));
        require(validatorRegistry.isValidator(msg.sender), "Not a validator");
        require(lastVotedNonce[idHash][msg.sender] < proposalNonce[idHash], "Already voted this round");
        require(!finalized[idHash], "Already finalized");

        lastVotedNonce[idHash][msg.sender] = proposalNonce[idHash];
        if (agree) {
            agreeVotes[idHash] += 1;
        } else {
            disagreeVotes[idHash] += 1;
        }

        uint256 totalValidators = validatorRegistry.getValidatorCount();
        uint256 threshold       = (2 * totalValidators + 2) / 3; // ceil(2/3 * TV)

        if (agreeVotes[idHash] >= threshold) {
            _finalize(idHash, settlementId, true);
        } else if (disagreeVotes[idHash] >= threshold) {
            _finalize(idHash, settlementId, false);
        }
    }

    function _finalize(bytes32 idHash, string calldata settlementId, bool didAgree) private {
        finalized[idHash] = true;

        // only lock out further attest() if the owner actually proposed Confirmed
        if (didAgree && settlements[idHash].status == Status.Confirmed) {
            confirmedLock[idHash] = true;
        }

        Status finalStatus = settlements[idHash].status;
        emit SettlementValidated(idHash, settlementId, finalStatus);
    }

    /// @notice return all settlement hashes
    function getSettlementIdHashes() external view returns (bytes32[] memory) {
        return settlementIdHashes;
    }

    /// @notice Return all idHashes for settlements this address paid for
    function getSettlementsByPayer(address payer)
        external
        view
        returns (bytes32[] memory)
        {
        return _settlementsByPayer[payer];
        }

    /// @notice Return all initialized settlement IDs
    function getSettlementIds() external view returns (string[] memory) {
        return settlementIds;
    }

    /// @notice read the full struct
    function getSettlement(bytes32 idHash) external view returns (Settlement memory) {
        return settlements[idHash];
    }

    /// @notice Lookup by human-readable ID, so callers don’t have to hash it themselves
    function getSettlementById(string calldata settlementId)
    external
    view
    returns (
        string memory _settlementId,
        string memory settlementType,
        Status        status,
        string memory metadata,
        uint256       amount,
        address       payer
    )
    {
        bytes32 idHash = keccak256(abi.encodePacked(settlementId));
        Settlement storage s = settlements[idHash];
        require(bytes(s.settlementId).length != 0, "Not found");
        return (
        s.settlementId,
        s.settlementType,
        s.status,
        s.metadata,
        s.amount,
        s.payer
        );
    }

    function getCounterparty(bytes32 idHash) external view returns (address) {
        return settlements[idHash].payer;
        }

    function isValidator(address _addr) public view returns (bool) {
        return validatorRegistry.isValidator(_addr);
    }
    function getValidatorCount() public view returns (uint256) {
        return validatorRegistry.getValidatorCount();
    }
}
