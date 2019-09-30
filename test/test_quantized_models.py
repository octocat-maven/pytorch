import torch
import torch.jit
from common_utils import run_tests, TEST_WITH_UBSAN, IS_PPC
from common_quantization import QuantizationTestCase, ModelMultipleOps, ModelMultipleOpsNoAvgPool
from common_quantized import override_quantized_engine

def test_float_quant_compare_per_tensor_op(self):
    torch.manual_seed(42)
    myModel = ModelMultipleOps().to(torch.float32)
    myModel.eval()
    calib_data = torch.rand(1024, 3, 15, 15, dtype=torch.float32)
    eval_data = torch.rand(1, 3, 15, 15, dtype=torch.float32)
    out_ref = myModel(eval_data)
    qModel = torch.quantization.QuantWrapper(myModel)
    qModel.eval()
    qModel.qconfig = torch.quantization.default_qconfig
    torch.quantization.fuse_modules(qModel.module, [['conv1', 'bn1', 'relu1']])
    torch.quantization.prepare(qModel, inplace=True)
    qModel(calib_data)
    torch.quantization.convert(qModel, inplace=True)
    out_q = qModel(eval_data)
    SQNRdB = 20 * torch.log10(torch.norm(out_ref) / torch.norm(out_ref - out_q))
    # Quantized model output should be close to floating point model output numerically
    # Setting target SQNR to be 30 dB so that relative error is 1e-3 below the desired
    # output
    self.assertGreater(SQNRdB, 30, msg='Quantized model numerics diverge from float, expect SQNR > 30 dB')

def test_fake_quant_true_quant_compare_op(self):
    torch.manual_seed(67)
    myModel = ModelMultipleOpsNoAvgPool().to(torch.float32)
    calib_data = torch.rand(2048, 3, 15, 15, dtype=torch.float32)
    eval_data = torch.rand(10, 3, 15, 15, dtype=torch.float32)
    myModel.eval()
    out_ref = myModel(eval_data)
    fqModel = torch.quantization.QuantWrapper(myModel)
    fqModel.train()
    fqModel.qconfig = torch.quantization.default_qat_qconfig
    torch.quantization.fuse_modules(fqModel.module, [['conv1', 'bn1', 'relu1']])
    torch.quantization.prepare_qat(fqModel)
    fqModel.eval()
    fqModel.apply(torch.quantization.disable_fake_quant)
    fqModel.apply(torch.nn._intrinsic.qat.freeze_bn_stats)
    fqModel(calib_data)
    fqModel.apply(torch.quantization.enable_fake_quant)
    fqModel.apply(torch.quantization.disable_observer)
    out_fq = fqModel(eval_data)
    SQNRdB = 20 * torch.log10(torch.norm(out_ref) / torch.norm(out_ref - out_fq))
    # Quantized model output should be close to floating point model output numerically
    # Setting target SQNR to be 35 dB
    self.assertGreater(SQNRdB, 35, msg='Quantized model numerics diverge from float, expect SQNR > 35 dB')
    torch.quantization.convert(fqModel)
    out_q = fqModel(eval_data)
    SQNRdB = 20 * torch.log10(torch.norm(out_fq) / (torch.norm(out_fq - out_q) + 1e-10))
    self.assertGreater(SQNRdB, 60, msg='Fake quant and true quant numerics diverge, expect SQNR > 60 dB')

# Test to compare weight only quantized model numerics and
# activation only quantized model numerics with float
def test_weight_only_activation_only_fakequant_op(self):
    torch.manual_seed(67)
    calib_data = torch.rand(2048, 3, 15, 15, dtype=torch.float32)
    eval_data = torch.rand(10, 3, 15, 15, dtype=torch.float32)
    qconfigset = set([torch.quantization.default_weight_only_quant_qconfig,
                      torch.quantization.default_activation_only_quant_qconfig])
    SQNRTarget = [35, 45]
    for idx, qconfig in enumerate(qconfigset):
        myModel = ModelMultipleOpsNoAvgPool().to(torch.float32)
        myModel.eval()
        out_ref = myModel(eval_data)
        fqModel = torch.quantization.QuantWrapper(myModel)
        fqModel.train()
        fqModel.qconfig = qconfig
        torch.quantization.fuse_modules(fqModel.module, [['conv1', 'bn1', 'relu1']])
        torch.quantization.prepare_qat(fqModel)
        fqModel.eval()
        fqModel.apply(torch.quantization.disable_fake_quant)
        fqModel.apply(torch.nn._intrinsic.qat.freeze_bn_stats)
        fqModel(calib_data)
        fqModel.apply(torch.quantization.enable_fake_quant)
        fqModel.apply(torch.quantization.disable_observer)
        out_fq = fqModel(eval_data)
        SQNRdB = 20 * torch.log10(torch.norm(out_ref) / torch.norm(out_ref - out_fq))
        self.assertGreater(SQNRdB, SQNRTarget[idx], msg='Quantized model numerics diverge from float')


class ModelNumerics(QuantizationTestCase):
    def test_float_quant_compare_per_tensor(self):
        if 'qnnpack' in torch.backends.quantized.supported_engines:
            if not IS_PPC and not TEST_WITH_UBSAN:
                with override_quantized_engine('qnnpack'):
                    test_float_quant_compare_per_tensor_op(self)
        if 'fbgemm' in torch.backends.quantized.supported_engines:
            with override_quantized_engine('fbgemm'):
                test_float_quant_compare_per_tensor_op(self)

    def test_float_quant_compare_per_channel(self):
        # Test for per-channel Quant
        torch.manual_seed(67)
        my_model = ModelMultipleOps().to(torch.float32)
        my_model.eval()
        calib_data = torch.rand(2048, 3, 15, 15, dtype=torch.float32)
        eval_data = torch.rand(10, 3, 15, 15, dtype=torch.float32)
        out_ref = my_model(eval_data)
        q_model = torch.quantization.QuantWrapper(my_model)
        q_model.eval()
        q_model.qconfig = torch.quantization.default_per_channel_qconfig
        torch.quantization.fuse_modules(q_model.module, [['conv1', 'bn1', 'relu1']])
        torch.quantization.prepare(q_model)
        q_model(calib_data)
        torch.quantization.convert(q_model)
        out_q = q_model(eval_data)
        SQNRdB = 20 * torch.log10(torch.norm(out_ref) / torch.norm(out_ref - out_q))
        # Quantized model output should be close to floating point model output numerically
        # Setting target SQNR to be 35 dB
        self.assertGreater(SQNRdB, 35, msg='Quantized model numerics diverge from float, expect SQNR > 35 dB')

    def test_fake_quant_true_quant_compare(self):
        if 'qnnpack' in torch.backends.quantized.supported_engines:
            if not IS_PPC and not TEST_WITH_UBSAN:
                with override_quantized_engine('qnnpack'):
                    test_fake_quant_true_quant_compare_op(self)
        if 'fbgemm' in torch.backends.quantized.supported_engines:
            with override_quantized_engine('fbgemm'):
                test_fake_quant_true_quant_compare_op(self)

    # Test to compare weight only quantized model numerics and
    # activation only quantized model numerics with float
    def test_weight_only_activation_only_fakequant(self):
        if 'qnnpack' in torch.backends.quantized.supported_engines:
            if not IS_PPC and not TEST_WITH_UBSAN:
                with override_quantized_engine('qnnpack'):
                    test_weight_only_activation_only_fakequant_op(self)
        if 'fbgemm' in torch.backends.quantized.supported_engines:
            with override_quantized_engine('fbgemm'):
                test_weight_only_activation_only_fakequant_op(self)

if __name__ == "__main__":
    run_tests()
