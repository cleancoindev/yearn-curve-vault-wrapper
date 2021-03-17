// SPDX-License-Identifier: MIT
pragma solidity ^0.6.12;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {VaultAPI, BaseWrapper} from "@yearnvaults/contracts/BaseWrapper.sol";
import {SafeMath} from "@openzeppelin/contracts/math/SafeMath.sol";

contract CurveVaultWrapper is ERC20, BaseWrapper {
    using SafeMath for uint256;

    /// @notice The EIP-712 typehash for the contract's domain
    bytes32 public constant DOMAIN_TYPEHASH =
        keccak256(
            "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
        );
    bytes32 public immutable DOMAIN_SEPARATOR;

    /// @notice The EIP-712 typehash for the permit struct used by the contract
    bytes32 public constant PERMIT_TYPEHASH =
        keccak256(
            "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
        );

    /// @notice A record of states for signing / validating signatures
    mapping(address => uint256) public nonces;

    address public governance;

    address public pendingGovernance;
    uint256 public lastReport;

    uint256 constant MAX_BPS = 10_000; // 100%, or 10k basis points
    uint256 constant SECS_PER_YEAR = 31_556_952; // 365.2425 days
    uint256 public managementFee = 200; // 2% per year

    modifier onlyGovernance() {
        require(msg.sender == governance);
        _;
    }

    constructor(
        address _token,
        address _registry,
        string memory name,
        string memory symbol
    ) public BaseWrapper(_token, _registry) ERC20(name, symbol) {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                DOMAIN_TYPEHASH,
                keccak256(bytes(name)),
                keccak256(bytes("1")),
                _getChainId(),
                address(this)
            )
        );
        lastReport = block.timestamp;
        governance = msg.sender;
        _setupDecimals(uint8(ERC20(address(token)).decimals()));
    }

    function _getChainId() internal view returns (uint256) {
        uint256 chainId;
        assembly {
            chainId := chainid()
        }
        return chainId;
    }

    function setGovernance(address _governance) external onlyGovernance {
        pendingGovernance = _governance;
    }

    function acceptGovernance() external {
        require(msg.sender == pendingGovernance);
        governance = msg.sender;
    }

    function _shareValue(uint256 numShares) internal view returns (uint256) {
        uint256 totalShares = totalSupply();

        if (totalShares > 0) {
            return
                totalVaultBalance(address(this)).mul(numShares).div(
                    totalShares
                );
        } else {
            return numShares;
        }
    }

    function pricePerShare() external view returns (uint256) {
        return 10**uint256(decimals());
    }

    function _sharesForValue(uint256 amount) internal view returns (uint256) {
        uint256 totalWrapperAssets = totalVaultBalance(address(this));

        if (totalWrapperAssets > 0) {
            return totalSupply().mul(amount).div(totalWrapperAssets);
        } else {
            return amount;
        }
    }

    function deposit() external returns (uint256) {
        return deposit(uint256(-1)); // Deposit everything
    }

    function deposit(uint256 amount) public returns (uint256 deposited) {
        _assessFees();
        uint256 shares = _sharesForValue(amount); // NOTE: Must be calculated before deposit is handled
        deposited = _deposit(msg.sender, address(this), amount, true); // `true` = pull from `msg.sender`
        _mint(msg.sender, shares);
    }

    function withdraw() external returns (uint256) {
        return withdraw(balanceOf(msg.sender));
    }

    function withdraw(uint256 shares) public returns (uint256) {
        _assessFees();
        _burn(msg.sender, shares);
        return _withdraw(address(this), msg.sender, _shareValue(shares), true); // `true` = withdraw from `bestVault`
    }

    function migrate() external onlyGovernance returns (uint256) {
        return _migrate(address(this));
    }

    function migrate(uint256 amount) external onlyGovernance returns (uint256) {
        return _migrate(address(this), amount);
    }

    function migrate(uint256 amount, uint256 maxMigrationLoss)
        external
        onlyGovernance
        returns (uint256)
    {
        return _migrate(address(this), amount, maxMigrationLoss);
    }

    function _assessFees() internal {
        if (totalSupply() == 0) {
            // Do not assesFees before the first deposit.
            lastReport = block.timestamp;
            return;
        }

        uint256 governance_fee =
            totalSupply()
                .mul(block.timestamp.sub(lastReport))
                .mul(managementFee)
                .div(MAX_BPS)
                .div(SECS_PER_YEAR);

        if (governance_fee != 0) {
            _mint(governance, governance_fee);
            lastReport = block.timestamp;
        }
    }

    function setManagementFee(uint256 _fee) external onlyGovernance {
        managementFee = _fee;
    }

    /**
     * @notice Triggers an approval from owner to spends
     * @param owner The address to approve from
     * @param spender The address to be approved
     * @param amount The number of tokens that are approved (2^256-1 means infinite)
     * @param deadline The time at which to expire the signature
     * @param v The recovery byte of the signature
     * @param r Half of the ECDSA signature pair
     * @param s Half of the ECDSA signature pair
     */
    function permit(
        address owner,
        address spender,
        uint256 amount,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(owner != address(0), "permit: signature");
        require(block.timestamp <= deadline, "permit: expired");

        bytes32 structHash =
            keccak256(
                abi.encode(
                    PERMIT_TYPEHASH,
                    owner,
                    spender,
                    amount,
                    nonces[owner]++,
                    deadline
                )
            );
        bytes32 digest =
            keccak256(
                abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash)
            );

        address signatory = ecrecover(digest, v, r, s);
        require(signatory == owner, "permit: unauthorized");

        _approve(owner, spender, amount);
    }
}
