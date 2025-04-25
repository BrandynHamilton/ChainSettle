pragma solidity ^0.8.20;

contract SettlementRegistry {
    address public owner;

    enum Status { Unverified, Confirmed, Failed }

    struct Settlement {
        string escrowId;
        Status status;
        string metadata; // could store tag, docURI, etc.
        uint256 amount; // optional; use 0 if not needed
    }

    mapping(string => Settlement) public settlements;

    event Attested(string escrowId, Status status, string metadata, uint256 amount);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Unauthorized");
        _;
    }

    function attest(
        string calldata escrowId,
        Status status,
        string calldata metadata,
        uint256 amount
    ) external onlyOwner {
        settlements[escrowId] = Settlement(escrowId, status, metadata, amount);
        emit Attested(escrowId, status, metadata, amount);
    }
}
