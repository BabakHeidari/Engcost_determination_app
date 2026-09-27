(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.BomCosting = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function requiredNumber(value, fieldName) {
        if (value === "" || value === null || value === undefined ||
                (typeof value === "string" && value.trim() === "")) {
            throw new TypeError(`${fieldName} الزامی است.`);
        }
        const number = Number(value);
        if (!Number.isFinite(number)) {
            throw new TypeError(`${fieldName} باید عدد معتبر باشد.`);
        }
        return number;
    }

    function percentage(value, fieldName) {
        const number = requiredNumber(value, fieldName);
        if (number < 0 || number > 100) {
            throw new RangeError(`${fieldName} باید بین ۰ و ۱۰۰ باشد.`);
        }
        return number;
    }

    function calculateEfficiencyFactor(lossPercentage, recyclabilityPercentage) {
        const lossFraction = percentage(lossPercentage, "درصد ضایعات") / 100;
        const recyclabilityFraction = percentage(recyclabilityPercentage, "درصد بازیافت‌پذیری") / 100;
        return 1 - (lossFraction * recyclabilityFraction);
    }

    function calculateLineCost({usage, unitPrice, fxFactor, lossPercentage, recyclabilityPercentage}) {
        const parsedUsage = requiredNumber(usage, "مصرف");
        const parsedPrice = requiredNumber(unitPrice, "قیمت واحد");
        const parsedFx = requiredNumber(fxFactor, "نرخ ارز");
        if (parsedUsage < 0) throw new RangeError("مصرف نمی‌تواند منفی باشد.");
        if (parsedPrice < 0) throw new RangeError("قیمت واحد نمی‌تواند منفی باشد.");
        if (parsedFx <= 0) throw new RangeError("نرخ ارز باید بزرگ‌تر از صفر باشد.");
        const efficiencyFactor = calculateEfficiencyFactor(lossPercentage, recyclabilityPercentage);
        const grossCostInRial = parsedUsage * parsedPrice * parsedFx;
        return {
            efficiencyFactor,
            grossCostInRial,
            liveCostInRial: grossCostInRial * efficiencyFactor
        };
    }

    return {calculateEfficiencyFactor, calculateLineCost, percentage, requiredNumber};
}));
