import brownie
import pytest
from brownie import chain
from eth_account import Account

AMOUNT = 100


def test_config(gov, token, vault, registry, curve_vault_wrapper):
    assert curve_vault_wrapper.token() == token
    assert curve_vault_wrapper.name() == "Yearn vault wrapper " + token.symbol()
    assert curve_vault_wrapper.symbol() == "Yvw" + token.symbol()
    assert curve_vault_wrapper.decimals() == vault.decimals() == token.decimals()

    # No vault added to the registry yet, so these methods should fail
    assert registry.numVaults(token) == 0

    with brownie.reverts():
        curve_vault_wrapper.bestVault()

    # This won't revert though, there's no Vaults yet
    assert curve_vault_wrapper.allVaults() == []

    # Now they work when we have a Vault
    registry.newRelease(vault, {"from": gov})
    registry.endorseVault(vault, {"from": gov})
    assert curve_vault_wrapper.bestVault() == vault
    assert curve_vault_wrapper.allVaults() == [vault]


def test_setGovernance(gov, curve_vault_wrapper, rando):
    new_gov = rando
    # No one can set governance but governance
    with brownie.reverts():
        curve_vault_wrapper.setGovernance(new_gov, {"from": new_gov})
    # Governance doesn't change until it's accepted
    curve_vault_wrapper.setGovernance(new_gov, {"from": gov})
    assert curve_vault_wrapper.governance() == gov
    # Only new governance can accept a change of governance
    with brownie.reverts():
        curve_vault_wrapper.acceptGovernance({"from": gov})
    # Governance doesn't change until it's accepted
    curve_vault_wrapper.acceptGovernance({"from": new_gov})
    assert curve_vault_wrapper.governance() == new_gov
    # No one can set governance but governance
    with brownie.reverts():
        curve_vault_wrapper.setGovernance(new_gov, {"from": gov})
    # Only new governance can accept a change of governance
    with brownie.reverts():
        curve_vault_wrapper.acceptGovernance({"from": gov})


def test_setRegistry(rando, gov, curve_vault_wrapper):
    with brownie.reverts():
        curve_vault_wrapper.setRegistry(rando, {"from": rando})

    with brownie.reverts():
        curve_vault_wrapper.setRegistry(rando, {"from": gov})

    # Only yGov can call this method
    curve_vault_wrapper.setRegistry(rando, {"from": gov})


def test_deposit(token, registry, vault, curve_vault_wrapper, gov, rando):
    registry.newRelease(vault, {"from": gov})
    registry.endorseVault(vault, {"from": gov})
    token.transfer(rando, 10000, {"from": gov})
    assert curve_vault_wrapper.balanceOf(rando) == vault.balanceOf(rando) == 0

    # NOTE: Must approve curve_vault_wrapper to deposit
    token.approve(curve_vault_wrapper, 10000, {"from": rando})
    curve_vault_wrapper.deposit(10000, {"from": rando})
    assert curve_vault_wrapper.balanceOf(rando) == 10000
    assert vault.balanceOf(rando) == 0


def test_migrate(token, registry, create_vault, curve_vault_wrapper, gov, rando):
    vault1 = create_vault(releaseDelta=1, token=token)
    registry.newRelease(vault1, {"from": gov})
    registry.endorseVault(vault1, {"from": gov})
    token.transfer(rando, 10000, {"from": gov})
    token.approve(curve_vault_wrapper, 10000, {"from": rando})
    curve_vault_wrapper.deposit(10000, {"from": rando})
    assert curve_vault_wrapper.balanceOf(rando) == 10000
    assert vault1.balanceOf(curve_vault_wrapper) == 10000

    vault2 = create_vault(releaseDelta=0, token=token)
    registry.newRelease(vault2, {"from": gov})
    registry.endorseVault(vault2, {"from": gov})

    with brownie.reverts():
        curve_vault_wrapper.migrate({"from": rando})

    # Only gov can call this method
    curve_vault_wrapper.migrate({"from": gov})
    assert curve_vault_wrapper.balanceOf(rando) == 10000
    assert vault1.balanceOf(curve_vault_wrapper) == 0
    assert vault2.balanceOf(curve_vault_wrapper) == 10000


def test_transfer(token, registry, vault, curve_vault_wrapper, gov, rando, user):
    registry.newRelease(vault, {"from": gov})
    registry.endorseVault(vault, {"from": gov})
    token.transfer(rando, 10000, {"from": gov})
    token.approve(curve_vault_wrapper, 10000, {"from": rando})
    curve_vault_wrapper.deposit(10000, {"from": rando})

    # NOTE: Just using `user` as a random address
    curve_vault_wrapper.transfer(user, 10000, {"from": rando})
    assert curve_vault_wrapper.balanceOf(rando) == 0
    assert curve_vault_wrapper.balanceOf(user) == 10000
    assert token.balanceOf(rando) == token.balanceOf(user) == 0


def test_withdraw(token, registry, vault, curve_vault_wrapper, gov, rando):
    registry.newRelease(vault, {"from": gov})
    registry.endorseVault(vault, {"from": gov})
    token.transfer(rando, 10000, {"from": gov})
    token.approve(curve_vault_wrapper, 10000, {"from": rando})
    curve_vault_wrapper.deposit(10000, {"from": rando})

    # NOTE: Must approve curve_vault_wrapper to withdraw
    curve_vault_wrapper.withdraw(10000, {"from": rando})
    assert curve_vault_wrapper.balanceOf(rando) == 0
    assert token.balanceOf(rando) == 10000


def test_permit(chain, rando, curve_vault_wrapper, sign_token_permit):
    owner = Account.create()
    deadline = chain[-1].timestamp + 3600
    signature = sign_token_permit(
        curve_vault_wrapper, owner, str(rando), allowance=AMOUNT, deadline=deadline
    )
    assert curve_vault_wrapper.allowance(owner.address, rando) == 0
    curve_vault_wrapper.permit(
        owner.address,
        rando,
        AMOUNT,
        deadline,
        signature.v,
        signature.r,
        signature.s,
        {"from": rando},
    )
    assert curve_vault_wrapper.allowance(owner.address, rando) == AMOUNT


def test_make_sure_gov_get_management_fee(
    token, registry, vault, curve_vault_wrapper, gov, rando, user
):
    registry.newRelease(vault, {"from": gov})
    registry.endorseVault(vault, {"from": gov})
    token.transfer(rando, 10000, {"from": gov})
    token.approve(curve_vault_wrapper, 10000, {"from": rando})
    curve_vault_wrapper.deposit(10000, {"from": rando})
    chain.sleep(3600 * 24 * 7)  # distributing 0.5 LP per day.
    curve_vault_wrapper.withdraw(10000, {"from": rando})

    assert curve_vault_wrapper.balanceOf(gov) != 0


def test_setManagementFee(gov, rando, curve_vault_wrapper):
    curve_vault_wrapper.setManagementFee(100, {"from": gov})
    assert curve_vault_wrapper.managementFee() == 100
    with brownie.reverts():
        curve_vault_wrapper.setManagementFee(0, {"from": rando})
